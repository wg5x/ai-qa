from datetime import date
from pathlib import Path

from openpyxl import Workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "samples"
QUOTE_HEADERS = [
    "客户名称",
    "国家/地区",
    "型号",
    "替换号码",
    "材质等级",
    "钢板厚度",
    "是否带减震片",
    "包装方式",
    "数量",
    "单价",
    "币种",
    "报价日期",
    "有效期",
    "备注",
]

CONTRACT_HEADERS = [
    "合同编号",
    "客户名称",
    "国家/地区",
    "下单日期",
    "型号",
    "材质等级",
    "包装方式",
    "数量",
    "单价",
    "币种",
    "交货期",
    "付款方式",
    "备注",
]

QUOTE_ROWS = [
    {
        "客户名称": "Ahmed",
        "国家/地区": "Libya",
        "型号": "D1234",
        "替换号码": "",
        "材质等级": "A+ 半金属",
        "钢板厚度": "",
        "是否带减震片": "",
        "包装方式": "彩盒",
        "数量": 1000,
        "单价": 2.30,
        "币种": "USD",
        "报价日期": date(2026, 7, 1),
        "有效期": "",
        "备注": "",
    },
    {
        "客户名称": "Ahmed",
        "国家/地区": "Libya",
        "型号": "D5678",
        "替换号码": "",
        "材质等级": "AA",
        "钢板厚度": "",
        "是否带减震片": "",
        "包装方式": "彩盒",
        "数量": 500,
        "单价": 3.10,
        "币种": "USD",
        "报价日期": date(2026, 7, 1),
        "有效期": "",
        "备注": "",
    },
]

CONTRACT_ROWS = [
    {
        "合同编号": "HT20260707001",
        "客户名称": "Ahmed",
        "国家/地区": "Libya",
        "下单日期": date(2026, 7, 7),
        "型号": "D1234",
        "材质等级": "A+ 半金属",
        "包装方式": "彩盒",
        "数量": 2000,
        "单价": 2.25,
        "币种": "USD",
        "交货期": "30天",
        "付款方式": "T/T",
        "备注": "首单",
    },
    {
        "合同编号": "HT20260707002",
        "客户名称": "Carlos",
        "国家/地区": "Brazil",
        "下单日期": date(2026, 7, 8),
        "型号": "D8888",
        "材质等级": "AAA",
        "包装方式": "中性包装",
        "数量": 800,
        "单价": 4.20,
        "币种": "USD",
        "交货期": "",
        "付款方式": "",
        "备注": "",
    },
]


def create_quote_sample(output_path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "报价单"
    sheet.append(QUOTE_HEADERS)
    for row in QUOTE_ROWS:
        sheet.append([row[header] for header in QUOTE_HEADERS])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path


def create_contract_sample(output_path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "合同"
    sheet.append(CONTRACT_HEADERS)
    for row in CONTRACT_ROWS:
        sheet.append([row[header] for header in CONTRACT_HEADERS])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path


if __name__ == "__main__":
    quote_sample_path = create_quote_sample(OUTPUT_DIR / "sample_quotes.xlsx")
    contract_sample_path = create_contract_sample(OUTPUT_DIR / "sample_contracts.xlsx")
    print(f"Created {quote_sample_path}")
    print(f"Created {contract_sample_path}")
