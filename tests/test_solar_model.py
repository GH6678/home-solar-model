# -*- coding: utf-8 -*-
"""solar_model 单元测试。运行: python -m pytest tests/ -v 或 python tests/test_solar_model.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.solar_model import (
    SolarSite,
    SystemConfig,
    SolarSystem,
    estimate_monthly_output,
    apply_degradation,
    load_config,
    load_site,
)


class TestOutput(unittest.TestCase):
    def test_monthly_output_formula(self):
        # 5kW x 100h x 0.8 = 400 kWh
        self.assertAlmostEqual(estimate_monthly_output(5.0, [100.0] * 12, 0.8)[0], 400.0)
        self.assertAlmostEqual(sum(estimate_monthly_output(5.0, [100.0] * 12, 0.8)), 4800.0)

    def test_monthly_length_validation(self):
        with self.assertRaises(ValueError):
            estimate_monthly_output(5.0, [100.0] * 11, 0.8)

    def test_positive_capacity_validation(self):
        with self.assertRaises(ValueError):
            estimate_monthly_output(0, [100.0] * 12, 0.8)

    def test_degradation_year1(self):
        # 首年 2% 衰减
        self.assertAlmostEqual(apply_degradation(1000, 1, 0.02, 0.0055), 980.0)

    def test_degradation_year2(self):
        # 第二年再乘 (1-0.0055)
        self.assertAlmostEqual(apply_degradation(1000, 2, 0.02, 0.0055), 980.0 * 0.9945, places=6)


class TestSystem(unittest.TestCase):
    def setUp(self):
        self.site = SolarSite(name="test", monthly_sunshine_hours=[100.0] * 12)
        self.cfg = SystemConfig(
            capacity_kw=5.0, system_efficiency=0.8, capex_per_watt=3.0,
            grid_price=0.5, feed_in_price=0.3, self_use_ratio=0.6,
            project_years=25,
        )
        self.sys = SolarSystem(self.site, self.cfg)

    def test_annual_output_year1(self):
        # 4800 kWh * 0.98 = 4704
        self.assertAlmostEqual(self.sys.annual_output(1), 4704.0, places=1)

    def test_yearly_benefit_breakdown(self):
        row = self.sys.yearly_benefit(1)
        # 自发自用 60%: 4704*0.6 = 2822.4 kWh @0.5 = 1411.2
        # 上网 40%: 4704*0.4 = 1881.6 kWh @0.3 = 564.48
        # 运维: 5*1000*3*0.005 = 75
        self.assertAlmostEqual(row["self_use_saving"], 1411.2, places=1)
        self.assertAlmostEqual(row["feed_in_income"], 564.48, places=1)
        self.assertAlmostEqual(row["opex"], 75.0, places=1)
        self.assertAlmostEqual(row["net_benefit"], 1900.68, places=1)

    def test_payback_with_high_price(self):
        # 高电价低投资时应快速回收
        cfg = SystemConfig(capacity_kw=5.0, capex_per_watt=2.0,
                           grid_price=0.8, feed_in_price=0.6, self_use_ratio=1.0)
        sys = SolarSystem(self.site, cfg)
        self.assertIsNotNone(sys.payback_years())
        self.assertLess(sys.payback_years(), 4)

    def test_payback_none_when_unprofitable(self):
        # 极端低价 + 高投资 + 高运维时 25 年无法回收
        cfg = SystemConfig(capacity_kw=5.0, capex_per_watt=10.0, opex_ratio=0.2,
                           grid_price=0.1, feed_in_price=0.0, self_use_ratio=0.0)
        sys = SolarSystem(self.site, cfg)
        self.assertIsNone(sys.payback_years())

    def test_cashflow_cumulative(self):
        rows = self.sys.cashflow()
        self.assertEqual(len(rows), 25)
        # 首年累计 = -初始投资 + 首年净收益
        capex = 5 * 1000 * 3.0
        self.assertAlmostEqual(rows[0]["cumulative_net"], -capex + rows[0]["net_benefit"], places=1)


class TestLoaders(unittest.TestCase):
    def test_load_config_defaults(self):
        cfg = load_config()
        self.assertEqual(cfg.capacity_kw, 5.0)
        self.assertEqual(cfg.project_years, 25)

    def test_load_config_json(self):
        import tempfile, json
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"capacity_kw": 8.0}, f)
            path = f.name
        try:
            cfg = load_config(path)
            self.assertEqual(cfg.capacity_kw, 8.0)
            self.assertEqual(cfg.grid_price, 0.55)  # 未覆盖的保持默认
        finally:
            os.unlink(path)

    def test_load_site_default(self):
        site = load_site()
        self.assertEqual(len(site.monthly_sunshine_hours), 12)

    def test_load_site_csv(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig", newline="") as f:
            f.write("month,hours\n")
            for i in range(1, 13):
                f.write(f"{i},{i*10.0}\n")
            path = f.name
        try:
            site = load_site(path)
            self.assertEqual(site.monthly_sunshine_hours[11], 120.0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
