# 1-95世共享页工作流

## 目标

早期世代 `1-95世` 不再为每个五世组重复准备 JPG。  
统一复用：

- [pages_jpg_qianbian_011_028](/Users/rainwu/Projects/FamilyGenealogyBook/pages_jpg_qianbian_011_028)

其中当前映射实际使用页：

- `11-28`

## 共享页原因

早期世代存在以下情况：

- 同一页会承载多个连续的五世组
- 部分五世组会跨两页

因此更适合：

1. 先准备共享 JPG 页资源
2. 再为每个五世组生成独立工作区
3. 每个工作区通过 `pages_data.image` 指向共享 JPG

## 配置文件

- [early_generation_groups_001_095.json](/Users/rainwu/Projects/FamilyGenealogyBook/configs/early_generation_groups_001_095.json)

## 批量初始化命令

```bash
python3 /Users/rainwu/Projects/FamilyGenealogyBook/scripts/prepare_shared_generation_groups.py
```

## 当前已覆盖的五世组

- `gen_001_005`
- `gen_006_010`
- `gen_011_015`
- `gen_016_020`
- `gen_021_025`
- `gen_026_030`
- `gen_031_035`
- `gen_036_040`
- `gen_041_045`
- `gen_046_050`
- `gen_051_055`
- `gen_056_060`
- `gen_061_065`
- `gen_066_070`
- `gen_071_075`
- `gen_076_080`
- `gen_081_085`
- `gen_086_090`
- `gen_091_095`
