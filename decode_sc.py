import os
from system.lib.swf import SupercellSWF


def _save_shap(swf: SupercellSWF, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    shapes_count = len(swf.shapes)
    for shape_index in range(shapes_count):
        shape = swf.shapes[shape_index]
        # rendered_shape = shape.render()
        # rendered_shape.save(f"{output_folder}/{shape.id}.png")
        regions_count = len(shape.regions)
        for region_index in range(regions_count):
            region = shape.regions[region_index]
            rendered_region = region.render(use_original_size=True)
            rendered_region.save(f"{output_folder}/shape_{shape.id}_{region_index}.png")


def decode_sc(input_folder, output_folder):
    for file in os.listdir(input_folder):
        if os.path.isdir(f"{input_folder}/{file}"):
            decode_sc(f"{input_folder}/{file}", f"{output_folder}/{file}")
        else:
            if file.endswith("_tex.sc") or not file.endswith(".sc"):
                continue
            # print('[*] Processing {}'.format(f.name))
            swf = SupercellSWF()
            file_name = os.path.join(input_folder, file)
            texture_loaded, use_lzham = swf.load(file_name)
            print(f"texture_loaded={texture_loaded}, use_lzham={use_lzham}")

            # 输出文件夹不存在则创建
            file_folder = os.path.join(output_folder, file)
            if not os.path.exists(file_folder):
                os.makedirs(file_folder)

            _save_shap(swf, file_folder)


def main():
    # input_folder = "./apk/clash-of-clans-16-253-20-tmp/assets/"
    input_folder = "./apk/clash-of-clans-16-253-20/assets/"
    # input_folder = "./apk/clash-of-clans-15-83-29/assets/"
    output_folder = "./output/"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    decode_sc(input_folder, output_folder)


if __name__ == "__main__":
    main()
