# Home Solar Model · 家庭小型光伏发电模型

一个面向家庭屋顶的分布式光伏发电 **设计与收益测算模型**：输入装机容量与日照数据，
输出逐月发电量、25 年现金流、投资回收期等指标。纯 Python 标准库实现，开箱即用。

## 功能特性

- ⚡ **发电量估算**：月/年发电量，考虑系统效率与逐年衰减（首年 2% + 年 0.55%）
- 💰 **收益测算**：自发自用节省 + 余电上网收入 - 运维成本，含 25 年累计净收益
- 📈 **投资回收期**：线性插值精度，自动判断是否可回收
- 📄 **现金流导出**：一键导出 25 年现金流 CSV
- 🛠 **可配置**：所有参数（容量、电价、自用比例、投资单价等）通过 JSON 配置

## 快速开始

```bash
# 运行默认模型（华北 5kW 屋顶系统）
python -m src.solar_model

# 自定义配置与日照数据
python -m src.solar_model --config config/defaults.json --site-csv data/sample_site.csv

# 运行单元测试
python tests/test_solar_model.py
# 或
python -m pytest tests/ -v
```

## 项目结构

```
home-solar-model/
├── README.md               # 项目说明
├── docs/
│   └── design.md           # 家庭光伏系统设计方案书
├── src/
│   └── solar_model.py      # 核心计算模型（发电量/收益/回收期）
├── config/
│   └── defaults.json       # 默认参数（华北 5kW）
├── data/
│   └── sample_site.csv     # 华北月日照示例数据
├── tests/
│   └── test_solar_model.py # 单元测试
├── requirements.txt
└── .gitignore
```

## 参数说明（config/defaults.json）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `capacity_kw` | 5.0 | 装机容量（kW） |
| `system_efficiency` | 0.80 | 系统效率（含各类损耗） |
| `capex_per_watt` | 3.20 | 初始投资（元/W） |
| `opex_ratio` | 0.005 | 年运维费率（占初始投资比例） |
| `grid_price` | 0.55 | 居民电价（元/kWh） |
| `feed_in_price` | 0.40 | 余电上网电价（元/kWh） |
| `self_use_ratio` | 0.70 | 自发自用比例 |
| `degradation_first_year` | 0.02 | 首年衰减 |
| `degradation_annual` | 0.0055 | 年衰减 |
| `project_years` | 25 | 测算年限 |

## 模型口径

```
月发电量(kWh)   = 装机容量(kW) × 当月峰值日照小时(h) × 系统效率
年发电量(kWh)   = Σ月发电量 × (1-衰减)
年收益(元)      = 自用电量×居民电价 + 上网电量×上网电价 - 运维成本
投资回收期      = 累计净收益首次 ≥ 0 的年份（线性插值）
```

## 默认结果速览（华北 5kW）

- 首年发电量：≈ 6,100 kWh
- 初始投资：≈ 16,000 元
- 投资回收期：≈ 5.4 年
- 25 年累计净收益：≈ 54,000 元

> 详细设计、选型与运维要点见 [docs/design.md](docs/design.md)。

## 免责声明

本项目仅用于教育、学习与初步测算，不构成投资建议。实际建设请委托有资质单位
进行现场勘察与设计，并遵循当地电网接入与备案政策。
