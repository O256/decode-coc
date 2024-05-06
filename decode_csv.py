# 读取文件夹文件，解析csv文件，输出到同目录
import os
from sc_compression import decompress


def decompress_csv(input_folder, output_folder):
    # 遍历文件夹，包括子目录
    for file in os.listdir(input_folder):
        if os.path.isdir(f"{input_folder}/{file}"):
            decompress_csv(f"{input_folder}/{file}", f"{output_folder}/{file}")
        else:

            # csv 文件结尾，且不是out开头
            if file.endswith(".csv"):
                # 检查output_folder是否存在，不存在就创建
                if not os.path.exists(output_folder):
                    os.makedirs(output_folder)

                with open(f"{input_folder}/{file}", "rb") as f:
                    file_data = f.read()
                    f.close()

                with open(f"{output_folder}/{file}", "wb") as f:
                    f.write(decompress(file_data)[0])
                    f.close()


def main():
    input_folder = "./apk/clash-of-clans-16-253-20/assets/"
    output_folder = "./output/"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    decompress_csv(input_folder, output_folder)


if __name__ == "__main__":
    main()
