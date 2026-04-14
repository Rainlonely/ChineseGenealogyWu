# 下一轮五世组准备流程

## 目标

把新的五世组先初始化为统一结构，后续继续沿用：

1. 原图渲染
2. 安全裁切
3. 生成 `group_template.json`
4. 生成 `workflow.md`
5. 生成 `review_template.md`
6. 再进入 OCR 与人工补链

## 初始化命令模板

```bash
python3 scripts/prepare_genealogy_group.py \
  --pdf "/Users/rainwu/Projects/FamilyGenealogyBook/2卷一-212页系92—107.pdf" \
  --out-dir "/Users/rainwu/Projects/FamilyGenealogyBook/gen_103_107" \
  --page-start 113 \
  --page-end 212 \
  --generations 103,104,105,106,107 \
  --label "103-107世"
```

## OCR 命令模板

```bash
python3 scripts/paddleocr_group_pages.py \
  --group-json "/Users/rainwu/Projects/FamilyGenealogyBook/gen_103_107/group_template.json" \
  --images-dir "/Users/rainwu/Projects/FamilyGenealogyBook/gen_103_107/cropped_jpg" \
  --out-dir "/Users/rainwu/Projects/FamilyGenealogyBook/gen_103_107/paddleocr_group"
```

## 当前轮次

- 组编号：`gen_103_107`
- 页码范围：`113-212`
- 世代范围：`103,104,105,106,107`
