import os
import lzma
import lzham
import zstandard
import struct

from loguru import logger
from sc_compression import compress, decompress
from sc_compression.signatures import Signatures

from system.localization import locale

from ktx import load_ktx


def write_sc(output_filename: str | os.PathLike, buffer: bytes, use_lzham: bool):
    with open(output_filename, "wb") as file_out:
        logger.info(locale.header_done)

        if use_lzham:
            logger.info(locale.compressing_with % "LZHAM")
            # Why is this here? It's included in the compression module
            # file_out.write(struct.pack("<4sBI", b"SCLZ", 18, len(buffer)))
            compressed = compress(buffer, Signatures.SCLZ)

            file_out.write(compressed)
        else:
            logger.info(locale.compressing_with % "LZMA")
            compressed = compress(buffer, Signatures.SC, 3)
            file_out.write(compressed)
        logger.info(locale.compression_done)
    print()


def open_sc(input_filename: str) -> tuple[bytes, bool]:
    use_lzham = False

    with open(input_filename, "rb") as f:
        file_data = f.read()
        f.close()

    try:
        if b"START" in file_data:
            file_data = file_data[: file_data.index(b"START")]
        decompressed_data, signature = decompress(file_data)

        if signature.name != Signatures.NONE:
            logger.info(locale.detected_comp % signature.name.upper())

        if signature == Signatures.SCLZ:
            use_lzham = True
    except TypeError:
        logger.info(locale.decompression_error)
        exit(1)

    return decompressed_data, use_lzham

def convert_pixel(pixel, type):
    if type == 0 or type == 1:
        # RGB8888
        return struct.unpack('4B', pixel)
    elif type == 2:
        # RGB4444
        pixel, = struct.unpack('<H', pixel)
        return (((pixel >> 12) & 0xF) << 4, ((pixel >> 8) & 0xF) << 4,
                ((pixel >> 4) & 0xF) << 4, ((pixel >> 0) & 0xF) << 4)
    elif type == 3:
        # RBGA5551
        pixel, = struct.unpack('<H', pixel)
        return (((pixel >> 11) & 0x1F) << 3, ((pixel >> 6) & 0x1F) << 3,
                ((pixel >> 1) & 0x1F) << 3, ((pixel) & 0xFF) << 7)
    elif type == 4:
        # RGB565
        pixel, = struct.unpack("<H", pixel)
        return (((pixel >> 11) & 0x1F) << 3, ((pixel >> 5) & 0x3F) << 2, (pixel & 0x1F) << 3)
    elif type == 6:
        # LA88 = Luminance Alpha 88
        pixel, = struct.unpack("<H", pixel)
        return (pixel >> 8), (pixel >> 8), (pixel >> 8), (pixel & 0xFF)
    elif type == 10:
        # L8 = Luminance8
        pixel, = struct.unpack("<B", pixel)
        return pixel, pixel, pixel
    elif type == 15:
        raise NotImplementedError("Pixel type 15 is not supported")
    else:
        raise Exception("Unknown pixel type {}.".format(type))

def decompress_tex(data):
    version = None
    if data[:2] == b'SC':
        # Skip the header if there's any
        pre_version = int.from_bytes(data[2: 6], 'big')

        if pre_version == 4:
            version = int.from_bytes(data[6: 10], 'big')
            hash_length = int.from_bytes(data[10: 14], 'big')
            end_block_size = int.from_bytes(data[-4:], 'big')

            data = data[14 + hash_length:-end_block_size - 9]

        else:
            version = pre_version
            hash_length = int.from_bytes(data[6: 10], 'big')
            data = data[10 + hash_length:]

    if version in (None, 1, 3):
        if data[:4] == b'SCLZ':
            print('[*] Detected LZHAM compression !')

            dict_size = int.from_bytes(data[4:5], 'big')
            uncompressed_size = int.from_bytes(data[5:9], 'little')
            decompressed = lzham.decompress(data[9:], uncompressed_size, {'dict_size_log2': dict_size})

        elif data[:4] == bytes.fromhex('28 B5 2F FD'):
            print('[*] Detected Zstandard compression !')
            decompressed = zstandard.decompress(data)

        else:
            print('[*] Detected LZMA compression !')
            data = data[0:9] + (b'\x00' * 4) + data[9:]
            decompressor = lzma.LZMADecompressor()

            output = []

            while decompressor.needs_input:
                output.append(decompressor.decompress(data))

            decompressed = b''.join(output)
    return decompressed


def open_tex_sc(input_filename: str) -> tuple[bytes, bool]:
    use_lzham = False

    with open(input_filename, "rb") as f:
        file_data = f.read()
        f.close()
    try:
        decompressed_data = decompress_tex(file_data)
        use_lzham = False
    except TypeError:
        print('[*] Decompression error !')
        exit(1)


    return decompressed_data, use_lzham
