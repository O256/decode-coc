import os
import struct
import liblzfse
from texture2ddecoder import decode_astc
from system.bytestream import Reader, Writer

from PIL import Image

from system.lib.images import (
    get_format_by_pixel_type,
    join_image,
    load_image_from_buffer,
    load_texture,
)


class SWFTexture:
    def __init__(self):
        self.width = 0
        self.height = 0

        self.pixel_type = -1

        self.image: Image.Image

    def load(self, swf, tag: int, has_texture: bool):
        self.pixel_type = swf.reader.read_char()
        self.width, self.height = (
            swf.reader.read_ushort(),
            swf.reader.read_ushort(),
        )

        if has_texture:
            img = Image.new(
                get_format_by_pixel_type(self.pixel_type), (self.width, self.height)
            )

            load_texture(swf.reader, self.pixel_type, img)

            if tag in (27, 28, 29):
                join_image(img)
            else:
                load_image_from_buffer(img)

            os.remove("pixel_buffer")

            self.image = img

    def read_ktx(reader: Reader):
        data = reader.read(64)
        print("[*] load_ktx")
        header = data[:64]
        ktx_data = data[64:]

        if header[12:16] == bytes.fromhex("01020304"):
            endianness = "<"

        else:
            endianness = ">"

        if header[0:7] != b"\xabKTX 11":
            raise TypeError(
                "Unsupported or unknown KTX version: {}".format(header[0:7])
            )

        (glInternalFormat,) = struct.unpack(endianness + "I", header[28:32])
        pixelWidth, pixelHeight = struct.unpack(endianness + "2I", header[36:44])
        (bytesOfKeyValueData,) = struct.unpack(endianness + "I", header[60:64])

        if glInternalFormat not in (0x93B0, 0x93B4, 0x93B7):
            raise TypeError(
                "Unsupported texture format: {}".format(hex(glInternalFormat))
            )

        if glInternalFormat == 0x93B0:
            block_width, block_height = 4, 4

        elif glInternalFormat == 0x93B4:
            block_width, block_height = 6, 6

        else:
            block_width, block_height = 8, 8

        ktx_data = reader.read(bytesOfKeyValueData)
        image_data = ktx_data[4:]

        decoded_data = decode_astc(
            image_data, pixelWidth, pixelHeight, block_width, block_height
        )
        return (
            Image.frombytes(
                "RGBA", (pixelWidth, pixelHeight), decoded_data, "raw", ("BGRA")
            ),
            bytesOfKeyValueData + 64,
        )

    def load_ktx(self, swf, tag: int, has_texture: bool):
        if has_texture:
            img = self.read_ktx(swf.reader)

            self.image = img
