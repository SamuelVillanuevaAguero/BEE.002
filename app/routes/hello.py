from fastapi import APIRouter

router = APIRouter()

@router.get("/test")
def hello_world():
    return {"message": "Hello world! I'm Bee 🐝🚀"}