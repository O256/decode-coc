import os
from typing import List, Tuple

from loguru import logger
import os
import lzma
import lzham
import zstandard
import struct

from PIL import Image
from ktx import load_ktx

from system.bytestream import Reader, Writer
from system.lib.features.files import open_sc
from system.lib.features.files import open_tex_sc
from system.lib.matrices.matrix_bank import MatrixBank
from system.lib.objects import MovieClip, Shape, SWFTexture
from system.localization import locale


def convert_pixel(pixel, type):
    if type == 0 or type == 1:
        # RGB8888
        return struct.unpack("4B", pixel)
    elif type == 2:
        # RGB4444
        (pixel,) = struct.unpack("<H", pixel)
        return (
            ((pixel >> 12) & 0xF) << 4,
            ((pixel >> 8) & 0xF) << 4,
            ((pixel >> 4) & 0xF) << 4,
            ((pixel >> 0) & 0xF) << 4,
        )
    elif type == 3:
        # RBGA5551
        (pixel,) = struct.unpack("<H", pixel)
        return (
            ((pixel >> 11) & 0x1F) << 3,
            ((pixel >> 6) & 0x1F) << 3,
            ((pixel >> 1) & 0x1F) << 3,
            ((pixel) & 0xFF) << 7,
        )
    elif type == 4:
        # RGB565
        (pixel,) = struct.unpack("<H", pixel)
        return (
            ((pixel >> 11) & 0x1F) << 3,
            ((pixel >> 5) & 0x3F) << 2,
            (pixel & 0x1F) << 3,
        )
    elif type == 6:
        # LA88 = Luminance Alpha 88
        (pixel,) = struct.unpack("<H", pixel)
        return (pixel >> 8), (pixel >> 8), (pixel >> 8), (pixel & 0xFF)
    elif type == 10:
        # L8 = Luminance8
        (pixel,) = struct.unpack("<B", pixel)
        return pixel, pixel, pixel
    elif type == 15:
        raise NotImplementedError("Pixel type 15 is not supported")
    else:
        raise Exception("Unknown pixel type {}.".format(type))


DEFAULT_HIGHRES_SUFFIX = "_highres"
DEFAULT_LOWRES_SUFFIX = "_lowres"


class SupercellSWF:
    TEXTURES_TAGS = (1, 16, 19, 24, 27, 28, 29, 3)
    SHAPES_TAGS = (2, 18)
    MOVIE_CLIPS_TAGS = (3, 10, 12, 14, 35)

    TEXTURE_EXTENSION = "_tex.sc"

    def __init__(self):
        self.filename: str
        self.reader: Reader

        self.use_lowres_texture: bool = False

        self.shapes: List[Shape] = []
        self.movie_clips: List[MovieClip] = []
        self.textures: List[SWFTexture] = []

        self.xcod_writer = Writer("big")

        self._filepath: str
        self._uncommon_texture_path: str

        self._lowres_suffix: str = DEFAULT_LOWRES_SUFFIX
        self._highres_suffix: str = DEFAULT_HIGHRES_SUFFIX

        self._use_uncommon_texture: bool = False

        self._shape_count: int = 0
        self._movie_clip_count: int = 0
        self._texture_count: int = 0
        self._text_field_count: int = 0

        self._export_count: int = 0
        self._export_ids: List[int] = []
        self._export_names: List[str] = []

        self._matrix_banks: List[MatrixBank] = []
        self._matrix_bank: MatrixBank

    def load(self, filepath: str | os.PathLike) -> Tuple[bool, bool]:
        self._filepath = str(filepath)

        texture_loaded, use_lzham = self._load_internal(
            self._filepath, self._filepath.endswith("_tex.sc")
        )

        if not texture_loaded:
            if self._use_uncommon_texture:
                texture_loaded, use_lzham = self._load_internal(
                    self._uncommon_texture_path, True
                )
            else:
                texture_path = self._filepath[:-3] + SupercellSWF.TEXTURE_EXTENSION
                texture_loaded, use_lzham = self._load_internal(texture_path, True)

        return texture_loaded, use_lzham

    def _load_texture(self, decompressed):
        i = 0
        texture_id = 0
        while len(decompressed[i:]) > 5:
            (fileType,) = struct.unpack("<b", bytes([decompressed[i]]))

            if fileType == 0x2D:
                i += 4  # Ignore this uint32, it's basically the fileSize + the size of subType + width + height (9 bytes)

            (fileSize,) = struct.unpack("<I", decompressed[i + 1 : i + 5])
            i += 5

            if fileType == 0x2F:
                zktx_path = decompressed[i + 1 : i + 1 + decompressed[i]].decode(
                    "utf-8"
                )
                i += decompressed[i] + 1

            (subType,) = struct.unpack("<b", bytes([decompressed[i]]))
            (width,) = struct.unpack("<H", decompressed[i + 1 : i + 3])
            (height,) = struct.unpack("<H", decompressed[i + 3 : i + 5])
            i += 5

            print(
                "fileType: {}, fileSize: {}, subType: {}, width: {}, "
                "height: {}".format(fileType, fileSize, subType, width, height)
            )

            if fileType != 0x2D and fileType != 0x2F:
                if subType in (0, 1):
                    pixelSize = 4
                elif subType in (2, 3, 4, 6):
                    pixelSize = 2
                elif subType == 10:
                    pixelSize = 1
                elif subType != 15:
                    raise Exception("Unknown pixel type {}.".format(subType))

                if subType == 15:
                    (ktx_size,) = struct.unpack("<I", decompressed[i : i + 4])
                    img = load_ktx(decompressed[i + 4 : i + 4 + ktx_size])
                    i += 4 + ktx_size

                else:
                    img = Image.new("RGBA", (width, height))
                    pixels = []

                    for y in range(height):
                        for x in range(width):
                            pixels.append(
                                convert_pixel(decompressed[i : i + pixelSize], subType)
                            )
                            i += pixelSize

                    img.putdata(pixels)

                if fileType == 29 or fileType == 28 or fileType == 27:
                    imgl = img.load()
                    iSrcPix = 0

                    for l in range(height // 32):  # block of 32 lines
                        # normal 32-pixels blocks
                        for k in range(width // 32):  # 32-pixels blocks in a line
                            for j in range(32):  # line in a multi line block
                                for h in range(32):  # pixels in a block
                                    imgl[h + (k * 32), j + (l * 32)] = pixels[iSrcPix]
                                    iSrcPix += 1
                        # line end blocks
                        for j in range(32):
                            for h in range(width % 32):
                                imgl[h + (width - (width % 32)), j + (l * 32)] = pixels[
                                    iSrcPix
                                ]
                                iSrcPix += 1
                    # final lines
                    for k in range(width // 32):  # 32-pixels blocks in a line
                        for j in range(height % 32):  # line in a multi line block
                            for h in range(32):  # pixels in a 32-pixels-block
                                imgl[h + (k * 32), j + (height - (height % 32))] = (
                                    pixels[iSrcPix]
                                )
                                iSrcPix += 1
                    # line end blocks
                    for j in range(height % 32):
                        for h in range(width % 32):
                            imgl[
                                h + (width - (width % 32)), j + (height - (height % 32))
                            ] = pixels[iSrcPix]
                            iSrcPix += 1

            else:
                img = load_ktx(decompressed[i : i + fileSize])
                i += fileSize

            if texture_id >= len(self.textures):
                self.textures.append(SWFTexture())

            texture = self.textures[texture_id]
            texture.image = img
            texture_id += 1

    def _load_internal(self, filepath: str, is_texture_file: bool) -> Tuple[bool, bool]:
        print("filepath=", filepath)
        self.filename = os.path.basename(filepath)

        logger.info(locale.collecting_inf % self.filename)

        # if is_texture_file:
        #     decompressed_data, use_lzham = open_tex_sc(filepath)
        #     self._load_texture(decompressed_data)
        #     return True, True
        # else:
        decompressed_data, use_lzham = open_sc(filepath)

        self.reader = Reader(decompressed_data)
        del decompressed_data

        if not is_texture_file:
            self._shape_count = self.reader.read_ushort()
            self._movie_clip_count = self.reader.read_ushort()
            self._texture_count = self.reader.read_ushort()
            self._text_field_count = self.reader.read_ushort()

            matrix_count = self.reader.read_ushort()
            color_transformation_count = self.reader.read_ushort()

            self._matrix_bank = MatrixBank()
            self._matrix_bank.init(matrix_count, color_transformation_count)
            self._matrix_banks.append(self._matrix_bank)

            self.shapes = [_class() for _class in [Shape] * self._shape_count]
            self.movie_clips = [
                _class() for _class in [MovieClip] * self._movie_clip_count
            ]
            self.textures = [_class() for _class in [SWFTexture] * self._texture_count]

            self.reader.read_uint()
            self.reader.read_char()

            self._export_count = self.reader.read_ushort()

            self._export_ids = []
            for _ in range(self._export_count):
                self._export_ids.append(self.reader.read_ushort())

            self._export_names = []
            for _ in range(self._export_count):
                self._export_names.append(self.reader.read_string())

        loaded = self._load_tags(is_texture_file)

        for i in range(self._export_count):
            export_id = self._export_ids[i]
            export_name = self._export_names[i]

            movie_clip = self.get_display_object(
                export_id, export_name, raise_error=True
            )

            if isinstance(movie_clip, MovieClip):
                movie_clip.export_name = export_name

        return loaded, use_lzham

    def _load_tags(self, is_texture_file: bool) -> bool:
        print("_load_tags=", is_texture_file)
        has_texture = True

        texture_id = 0
        movie_clips_loaded = 0
        shapes_loaded = 0
        matrices_loaded = 0

        tag_cout_dict = {}
        tag_count = 0
        while True:
            tag = self.reader.read_char()
            length = self.reader.read_uint()
            tag_count += 1

            # print("tag=%d,length=%d" % (tag, length))
            if not tag_cout_dict.get(tag):
                tag_cout_dict[tag] = 0
            tag_cout_dict[tag] += 1

            if tag == 0:
                # print("tag_count=", tag_count)
                for key, value in tag_cout_dict.items():
                    print(self.filename, key, value)
                return has_texture
            elif tag in SupercellSWF.TEXTURES_TAGS:
                # this is done to avoid loading the data file
                # (although it does not affect the speed)
                if is_texture_file and texture_id >= len(self.textures):
                    self.textures.append(SWFTexture())
                texture = self.textures[texture_id]
                texture.load(self, tag, has_texture)
                texture_id += 1
            elif tag in SupercellSWF.SHAPES_TAGS:
                self.shapes[shapes_loaded].load(self, tag)
                shapes_loaded += 1
            elif tag in SupercellSWF.MOVIE_CLIPS_TAGS:  # MovieClip
                self.movie_clips[movie_clips_loaded].load(self, tag)
                movie_clips_loaded += 1
            elif tag == 8 or tag == 36:  # Matrix
                self._matrix_bank.get_matrix(matrices_loaded).load(self.reader, tag)
                matrices_loaded += 1
            elif tag == 26:
                has_texture = False
            elif tag == 30:
                self._use_uncommon_texture = True
                highres_texture_path = (
                    self._filepath[:-3]
                    + self._highres_suffix
                    + SupercellSWF.TEXTURE_EXTENSION
                )
                lowres_texture_path = (
                    self._filepath[:-3]
                    + self._lowres_suffix
                    + SupercellSWF.TEXTURE_EXTENSION
                )

                self._uncommon_texture_path = highres_texture_path
                if not os.path.exists(highres_texture_path) and os.path.exists(
                    lowres_texture_path
                ):
                    self._uncommon_texture_path = lowres_texture_path
                    self.use_lowres_texture = True
            elif tag == 42:
                matrix_count = self.reader.read_ushort()
                color_transformation_count = self.reader.read_ushort()

                self._matrix_bank = MatrixBank()
                self._matrix_bank.init(matrix_count, color_transformation_count)
                self._matrix_banks.append(self._matrix_bank)

                matrices_loaded = 0
            elif tag == 45:
                # print("ktx=>", length)
                # self.reader.read_uint()
                file_size = self.reader.read_uint()

                subType = self.reader.read_char()
                width = self.reader.read_ushort()
                height = self.reader.read_ushort()

                data = self.reader.read(file_size)
                image = load_ktx(data)

                if texture_id >= len(self.textures):
                    self.textures.append(SWFTexture())

                texture = self.textures[texture_id]
                texture.height = height
                texture.width = width
                texture.image = image
                texture_id += 1
            else:
                self.reader.read(length)

    def get_display_object(
        self, target_id: int, name: str | None = None, *, raise_error: bool = False
    ) -> Shape | MovieClip | None:
        for shape in self.shapes:
            if shape.id == target_id:
                return shape

        for movie_clip in self.movie_clips:
            if movie_clip.id == target_id:
                return movie_clip

        if raise_error:
            exception_text = (
                f"Unable to find some DisplayObject id {target_id}, {self.filename}"
            )
            if name is not None:
                exception_text += f" needed by export name {name}"

            raise ValueError(exception_text)
        return None

    def get_matrix_bank(self, index: int) -> MatrixBank:
        return self._matrix_banks[index]
