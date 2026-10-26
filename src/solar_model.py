# -*- coding: utf-8 -*-
"""
家庭小型光伏发电模型 (Home Solar Model)

估算屋顶分布式光伏系统的：
  1. 发电量（月/年，考虑系统效率与逐年衰减）
  2. 经济收益（自发自用节省 + 余电上网收入 - 运维成本）
  3. 投资回收期与 25 年累计净收益

模型口径
--------
- 月发电量(kWh) = 装机容量(kW) x 当月峰值日照小时(h) x 系统效率
- 年发电量(kWh) = Σ 月发电量（逐年按衰减率递减）
- 年收益(元)   = 自发自用电量 x 居民电价 + 余电上网电量 x 上网电价 - 运维成本
- 投资回收期    = 累计净收益首次 >= 0 的年份（整数年）

用法
----
    命令行: python -m src.solar_model --config config/defaults.json
    库方式:  from src.solar_model import SolarSystem, run_simulation
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class SolarSite:
    """站点日照数据。monthly_sunshine_hours: 12 个元素的月峰值日照小时数列表。"""

    name: str = "华北-默认"
    monthly_sunshine_hours: List[float] = field(
        default_factory=lambda: [
            86.8, 92.4, 130.2, 156.0, 182.9, 171.0,
            155.0, 145.7, 138.0, 124.0, 93.0, 80.6,
        ]
    )

    @property
    def annual_sunshine_hours(self) -> float:
        return sum(self.monthly_sunshine_hours)


@dataclass
class SystemConfig:
    """系统与经济参数（单位：容量 kW、价格 元/W、电价 元/kWh、比例 0-1）。"""

    capacity_kw: float = 5.0
    system_efficiency: float = 0.80
    capex_per_watt: float = 3.20          # 初始投资（含组件/逆变器/支架/安装）
    opex_ratio: float = 0.005             # 年运维成本 = 初始投资 x 比例
    grid_price: float = 0.55              # 居民电价（元/kWh，自发自用部分）
    feed_in_price: float = 0.40           # 余电上网电价（元/kWh）
    self_use_ratio: float = 0.70          # 自发自用比例，其余上网
    degradation_first_year: float = 0.02  # 首年衰减
    degradation_annual: float = 0.0055    # 之后每年衰减
    project_years: int = 25
    export_results: bool = True           # 是否输出 CSV 现金流表


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------
def estimate_monthly_output(capacity_kw: float, monthly_sunshine: List[float],
                            efficiency: float) -> List[float]:
    """月发电量(kWh) = 容量(kW) x 峰值日照小时(h) x 系统效率。"""
    if len(monthly_sunshine) != 12:
        raise ValueError("monthly_sunshine 必须包含 12 个月的数值")
    if capacity_kw <= 0 or not (0 < efficiency <= 1):
        raise ValueError("容量必须为正数，效率必须在 (0, 1]")
    return [capacity_kw * h * efficiency for h in monthly_sunshine]


def apply_degradation(year_output_kwh: float, year: int,
                      first_year: float, annual: float) -> float:
    """计算第 year 年（1 起）发电量，含首年与逐年衰减。"""
    if year == 1:
        return year_output_kwh * (1 - first_year)
    return year_output_kwh * (1 - first_year) * ((1 - annual) ** (year - 1))


class SolarSystem:
    """由站点 + 配置构成的完整家庭光伏系统模型。"""

    def __init__(self, site: SolarSite, config: SystemConfig):
        self.site = site
        self.config = config
        self._year0_output_kwh = sum(
            estimate_monthly_output(config.capacity_kw, site.monthly_sunshine_hours,
                                    config.system_efficiency)
        )

    # -- 发电量 -------------------------------------------------------------
    def monthly_output(self) -> List[float]:
        return estimate_monthly_output(
            self.config.capacity_kw, self.site.monthly_sunshine_hours,
            self.config.system_efficiency,
        )

    def annual_output(self, year: int) -> float:
        """第 year 年发电量(kWh)。"""
        if year < 1:
            raise ValueError("year 从 1 开始")
        return apply_degradation(
            self._year0_output_kwh, year,
            self.config.degradation_first_year, self.config.degradation_annual,
        )

    # -- 收益 ---------------------------------------------------------------
    def yearly_benefit(self, year: int) -> Dict[str, float]:
        """第 year 年收益明细（元）。"""
        c = self.config
        output = self.annual_output(year)
        self_use = output * c.self_use_ratio
        feed_in = output * (1 - c.self_use_ratio)
        capex = c.capacity_kw * 1000 * c.capex_per_watt
        opex = capex * c.opex_ratio
        return {
            "year": year,
            "output_kwh": round(output, 1),
            "self_use_kwh": round(self_use, 1),
            "feed_in_kwh": round(feed_in, 1),
            "self_use_saving": round(self_use * c.grid_price, 2),
            "feed_in_income": round(feed_in * c.feed_in_price, 2),
            "opex": round(opex, 2),
            "net_benefit": round(self_use * c.grid_price + feed_in * c.feed_in_price - opex, 2),
        }

    def cashflow(self) -> List[Dict[str, float]]:
        """25 年现金流表（含初始投资、累计净收益）。"""
        c = self.config
        capex = c.capacity_kw * 1000 * c.capex_per_watt
        rows, cum = [], -capex
        for year in range(1, c.project_years + 1):
            row = self.yearly_benefit(year)
            cum += row["net_benefit"]
            row["cumulative_net"] = round(cum, 2)
            rows.append(row)
        return rows

    def payback_years(self) -> Optional[float]:
        """投资回收期（年）。未回收返回 None；在回收当年给出线性插值精度。"""
        c = self.config
        capex = c.capacity_kw * 1000 * c.capex_per_watt
        cum = -capex
        prev_cum = cum
        for year in range(1, c.project_years + 1):
            row = self.yearly_benefit(year)
            cum += row["net_benefit"]
            if cum >= 0:
                fraction = prev_cum / (prev_cum - cum) if cum != prev_cum else 1.0
                return round(year - 1 + fraction, 2)
            prev_cum = cum
        return None

    # -- 汇总 ---------------------------------------------------------------
    def summary(self) -> Dict[str, object]:
        rows = self.cashflow()
        pb = self.payback_years()
        return {
            "site": self.site.name,
            "capacity_kw": self.config.capacity_kw,
            "annual_output_year1_kwh": round(rows[0]["output_kwh"], 1),
            "annual_output_year25_kwh": round(rows[-1]["output_kwh"], 1),
            "total_output_25y_kwh": round(sum(r["output_kwh"] for r in rows), 0),
            "initial_investment": round(self.config.capacity_kw * 1000 * self.config.capex_per_watt, 2),
            "avg_annual_net_benefit": round(sum(r["net_benefit"] for r in rows) / len(rows), 2),
            "payback_years": pb,
            "cumulative_net_25y": round(rows[-1]["cumulative_net"], 2),
            "roe_25y_pct": round(rows[-1]["cumulative_net"]
                                 / (self.config.capacity_kw * 1000 * self.config.capex_per_watt) * 100, 1),
        }


# ---------------------------------------------------------------------------
# 加载与输出
# ---------------------------------------------------------------------------
def load_config(json_path: Optional[Path] = None) -> SystemConfig:
    """从 JSON 加载配置；未提供则使用默认值。"""
    cfg = SystemConfig()
    if json_path and Path(json_path).exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    return cfg


def load_site(csv_path: Optional[Path] = None) -> SolarSite:
    """从 CSV 加载月日照数据；未提供则使用华北默认值。

    CSV 格式（可含表头）：两列 month,hours（取 hours 列），或单列 12 个数值。
    """
    site = SolarSite()
    if csv_path and Path(csv_path).exists():
        values: List[float] = []
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                cell = (row[1] if len(row) >= 2 else row[0]).strip()
                if not cell:
                    continue
                try:
                    values.append(float(cell))
                except ValueError:
                    continue  # 跳过表头等非数值行
        if len(values) == 12 and all(v >= 0 for v in values):
            site.monthly_sunshine_hours = values
    return site


def export_cashflow_csv(rows: List[Dict[str, float]], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="家庭小型光伏发电模型")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "defaults.json",
                        help="系统配置 JSON 路径")
    parser.add_argument("--site-csv", type=Path, default=PROJECT_ROOT / "data" / "sample_site.csv",
                        help="月日照数据 CSV 路径")
    parser.add_argument("--output-csv", type=Path, default=None,
                        help="现金流表输出 CSV 路径（默认输出到 results/cashflow.csv）")
    args = parser.parse_args(argv)

    site = load_site(args.site_csv)
    cfg = load_config(args.config)
    system = SolarSystem(site, cfg)

    print(f"\n===== 家庭小型光伏发电模型 =====")
    print(f"站点: {site.name}   装机容量: {cfg.capacity_kw} kW")
    print(f"年等效利用小时(首年): {system._year0_output_kwh / cfg.capacity_kw:.0f} h")
    print(f"首年发电量: {system.annual_output(1):.0f} kWh")

    print("\n--- 月发电量（首年）---")
    for i, kwh in enumerate(system.monthly_output(), 1):
        print(f"  {i:>2}月: {kwh:8.1f} kWh")

    summary = system.summary()
    print("\n--- 经济性汇总 ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    if cfg.export_results:
        out = args.output_csv or (PROJECT_ROOT / "results" / "cashflow.csv")
        export_cashflow_csv(system.cashflow(), out)
        print(f"\n现金流明细已导出: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
