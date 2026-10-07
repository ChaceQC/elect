"""学校已缴费明细的只读契约。"""

from uuid import UUID

from services.common.dto import DTO, Count, DateRange, Money, Timestamp


class PaymentRecordsQuery(DateRange):
    binding_id: UUID


class PaymentRecord(DTO):
    id: str
    paid_at: Timestamp | None
    created_at: Timestamp
    amount: Money
    method: str | None


class PaymentRecords(DTO):
    items: list[PaymentRecord]
    total: Count
    total_amount: Money | None
    known_amount: Money
    complete: bool
