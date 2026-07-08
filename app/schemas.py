from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class SpeechTemplateStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DISABLED = "disabled"


class QuoteRecordBase(BaseModel):
    customer_name: str | None = None
    country: str | None = None
    part_number: str | None = None
    replacement_numbers: str | None = None
    material_grade: str | None = None
    steel_thickness: str | None = None
    has_shim: bool | None = None
    packaging: str | None = None
    quantity: int | None = None
    unit_price: Decimal | None = None
    currency: str | None = None
    quote_date: date | None = None
    valid_until: date | None = None
    remark: str | None = None
    source_file: str | None = None


class QuoteRecordRead(QuoteRecordBase):
    id: int
    created_at: datetime


class ContractRecordBase(BaseModel):
    contract_no: str | None = None
    customer_name: str | None = None
    country: str | None = None
    order_date: date | None = None
    part_number: str | None = None
    material_grade: str | None = None
    packaging: str | None = None
    quantity: int | None = None
    unit_price: Decimal | None = None
    currency: str | None = None
    delivery_time: str | None = None
    payment_terms: str | None = None
    remark: str | None = None
    source_file: str | None = None


class ContractRecordRead(ContractRecordBase):
    id: int
    created_at: datetime


class MaterialBase(BaseModel):
    name: str | None = None
    file_path: str | None = None
    material_type: str | None = None
    product_type: str | None = None
    scenario: str | None = None
    brand: str | None = None
    material_grade: str | None = None
    description: str | None = None
    recommended_script: str | None = None
    tags: str | None = None


class MaterialRead(MaterialBase):
    id: int
    created_at: datetime


class SpeechTemplateBase(BaseModel):
    scenario: str | None = None
    customer_question: str | None = None
    style_notes: str | None = None
    standard_reply: str | None = None
    forbidden_words: str | None = None
    recommended_material_ids: str | None = None
    status: SpeechTemplateStatus = SpeechTemplateStatus.DRAFT
    source_chat: str | None = None
    confirmed_at: datetime | None = None


class SpeechTemplateRead(SpeechTemplateBase):
    id: int
    created_at: datetime
