# --- 1. 导入必要的库 ---
from io import BytesIO  # 用于在内存中读写 "字节" 数据，这里用来保存最终的PNG图片
from typing import Tuple, Literal, Union # 用于 "类型提示"，让代码更易读
from PIL import Image # 导入Pillow库，用于 "打开/创建图片"、"P图"、"保存图片"
import os # 用于检查文件是否存在 (例如遮罩图片)

# --- 2. 定义类型别名 (让代码更清晰) ---
# 'Align' 只允许是 "left"、"center"、"right" 三个字符串之一
Align = Literal["left", "center", "right"]
# 'VAlign' 只允许是 "top"、"middle"、"bottom" 三个字符串之一
VAlign = Literal["top", "middle", "bottom"]

def paste_image_auto(
    # --- 3. 函数参数定义 ---
    image_source: Union[str, Image.Image], # 底图：可以是一个 "文件路径" (str)，也可以是 "已打开的Pillow图片" (Image.Image)
    top_left: Tuple[int, int],              # (x1, y1) 矩形区域的 "左上角" 坐标
    bottom_right: Tuple[int, int],          # (x2, y2) 矩形区域的 "右下角" 坐标
    content_image: Image.Image,             # "要粘贴" 的那张图片 (必须是 "已打开的Pillow图片" 对象)
    align: Align = "center",                # 水平对齐方式
    valign: VAlign = "middle",              # 垂直对齐方式
    padding: int = 0,                       # 在 "矩形区域" 内部留出的 "边距"
    allow_upscale: bool = False,            # "是否允许" 将 "小图" "放大" (如果为False，小图最多1:1)
    keep_alpha: bool = True,                # "是否保留" "要粘贴" 图片的 "透明" 通道
    image_overlay: Union[str, Image.Image, None]=None, # "可选"：一个 "遮罩" 图片，会覆盖在 "最上层"
) -> bytes: # "返回值"：函数最终会返回 "PNG图片的字节流" (bytes)
    """
    函数文档：
    在指定矩形内放置一张图片（content_image），按比例缩放至“最大但不超过”该矩形。
    - image_source (base_image): 底图（会被复制，原图不改）
    - top_left / bottom_right: 指定矩形区域（左上/右下坐标）
    - content_image: 待放入的图片（PIL.Image.Image）
    - align / valign: 水平/垂直对齐方式
    - padding: 矩形内边距（像素），四边统一
    - allow_upscale: 是否允许放大（默认只缩小不放大）
    - keep_alpha: True 时保留透明通道并用其作为粘贴蒙版

    返回：最终 PNG 的 bytes。
    """

    # --- 4. 验证 "输入" ---
    if not isinstance(content_image, Image.Image):
        # 确保 "要粘贴" 的 content_image 是一个 "Pillow图片对象"，而不是路径
        raise TypeError("content_image 必须为 PIL.Image.Image")

    # --- 5. 准备 "底图" ---
    if isinstance(image_source, Image.Image):
        # 如果传入的是 "Pillow图片对象"，就 "复制" 一份来用 (防止修改原图)
        img = image_source.copy()
    else:
        # 如果传入的是 "文件路径" (str)，就 "打开" 它
        # .convert("RGBA") 确保图片是 RGBA 模式，这样可以处理透明度
        img = Image.open(image_source).convert("RGBA")

    # --- 6. 准备 "遮罩" ---
    if image_overlay is not None:
        if isinstance(image_overlay, Image.Image):
            img_overlay = image_overlay.copy() # 同上，复制一份
        else:
            # 如果是路径，就打开它。如果文件不存在 (os.path.isfile)，就设为 None
            img_overlay = Image.open(image_overlay).convert("RGBA") if os.path.isfile(image_overlay) else None

    # --- 7. 计算 "粘贴区域" ---
    x1, y1 = top_left
    x2, y2 = bottom_right
    if not (x2 > x1 and y2 > y1):
        # 如果坐标不合法 (例如右下角在左上角上面)，就报错
        raise ValueError("无效的粘贴区域。")

    # "可用" 区域 = "总区域" 减去 "两边" 的 "边距" (padding)
    region_w = max(1, (x2 - x1) - 2 * padding) # (最少 1px 宽)
    region_h = max(1, (y2 - y1) - 2 * padding) # (最少 1px 高)

    # --- 8. 计算 "缩放比例" ---
    # 这是 "等比例" 缩放的核心
    
    # 1. 获取 "要粘贴" 图片的 "原始" 宽高
    cw, ch = content_image.size
    if cw <= 0 or ch <= 0:
        raise ValueError("content_image 尺寸无效。")

    # 2. "分别" 计算 "宽度" 和 "高度" 的 "缩放比"
    scale_w = region_w / cw  # (例如 区域 800 / 图片 1600 = 0.5)
    scale_h = region_h / ch  # (例如 区域 600 / 图片 1200 = 0.5)
    
    # 3. "关键"：取 "更小" 的那个比例
    #    (例如 区域 800x600, 图片 1600x600 -> scale_w=0.5, scale_h=1.0 -> 取 0.5)
    #    (这确保了图片 "完整" 地 "塞" 进 (contain) 区域，"不会" 超出)
    scale = min(scale_w, scale_h)

    # 4. (可选) "限制" 放大
    if not allow_upscale:
        # 如果 "不允许放大" (默认)，那么 "缩放比" (scale) "最大" 只能是 1.0 (原图大小)
        scale = min(1.0, scale)

    # 5. "计算" "缩放后" 的 "新" 宽高
    new_w = max(1, int(round(cw * scale))) # (最少 1px)
    new_h = max(1, int(round(ch * scale))) # (最少 1px)

    # --- 9. "执行" 缩放 ---
    # .resize() 会创建一张 "新" 的图片
    # Image.LANCZOS 是一种 "高质量" 的 "插值" 算法，(尤其适合 "缩小" 图片)
    resized = content_image.resize((new_w, new_h), Image.LANCZOS)

    # --- 10. 计算 "粘贴坐标" (考虑对齐) ---
    
    # 'px' (paste_x) 是 "粘贴" 到 "底图" 上的 "左上角 x" 坐标
    if align == "left":
        px = x1 + padding # 靠左
    elif align == "center":
        # 居中 = 区域左侧 + ( (可用宽度 - 图片新宽度) / 2 )
        px = x1 + padding + (region_w - new_w) // 2
    else:  # "right"
        # 靠右 = 区域右侧 - 边距 - 图片新宽度
        px = x2 - padding - new_w

    # 'py' (paste_y) 是 "粘贴" 到 "底图" 上的 "左上角 y" 坐标
    if valign == "top":
        py = y1 + padding # 靠上
    elif valign == "middle":
        # 居中 = 区域顶部 + ( (可用高度 - 图片新高度) / 2 )
        py = y1 + padding + (region_h - new_h) // 2
    else:  # "bottom"
        # 靠下 = 区域底部 - 边距 - 图片新高度
        py = y2 - padding - new_h

    # --- 11. "执行" 粘贴 (处理 "透明度") ---
    
    # "关键"：检查 "缩放后" (resized) 的图片 "是否" 包含 "透明" 通道 ("A")
    if keep_alpha and ("A" in resized.getbands()):
        # 1. "如果" 保留透明度，且图片 "有" 透明度：
        #    使用 'img.paste(图片, 坐标, 蒙版)'
        #    第3个参数 'resized' (图片自己) 会被用作 "蒙版" (Mask)
        #    Pillow 会自动 "只" 粘贴 "不透明" 的部分，实现 "完美" 透明
        img.paste(resized, (px, py), resized)
    else:
        # 2. "如果" 不保留透明度，或图片 "没有" 透明度：
        #    使用 'img.paste(图片, 坐标)'
        #    这会 "直接" 把 "矩形" (new_w x new_h) 区域 "覆盖" 到底图上
        img.paste(resized, (px, py))

    # --- 12. 绘制 "遮罩" (在 "粘贴" 完成之后) ---
    if image_overlay is not None and img_overlay is not None:
        # 1. 'img.paste(遮罩, 坐标, 遮罩)'
        #    第3个参数 'img_overlay' 表示 "使用 '遮罩' 自己的透明通道"
        #    这样 "遮罩" 的 "透明" 部分 "不会" 覆盖 "底图"
        #    坐标 (0, 0) 表示 "覆盖" "整张" 底图
        img.paste(img_overlay, (0, 0), img_overlay)
    elif image_overlay is not None and img_overlay is None:
        # (如果指定了遮罩路径，但文件不存在)
        print("Warning: overlay image is not exist.")

    # --- 13. "输出" 最终图片 ---
    
    # 1. 创建一个 "内存中" 的 "文件"
    buf = BytesIO()
    # 2. "保存" P好的图片 (img) 到 "内存" (buf) 中，格式为 "PNG"
    img.save(buf, format="PNG")
    # 3. "返回" 内存中 PNG 文件的 "所有字节" (bytes)
    return buf.getvalue()
