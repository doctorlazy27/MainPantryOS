from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate
from app.auth.dependencies import require_permission


router = APIRouter(
    prefix="/customers",
    tags=["Customers"]
)


@router.post("/")
def create_customer(
    customer: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_customers"))
):
    new_customer = Customer(
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        address=customer.address,
        warehouse_id=current_user.get("warehouse_id"),
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    return new_customer


@router.get("/")
def get_customers(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_customers"))):
    customers = db.query(Customer).filter(Customer.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "customers": customers
    }