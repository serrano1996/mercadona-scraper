from pydantic import BaseModel


class ProductQuery(BaseModel):
    postal_code: str
    term: str
