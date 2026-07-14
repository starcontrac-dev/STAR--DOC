import asyncio
import sys
import os

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import select
from app.database import async_session_maker
from app.models.user import User

async def list_users():
    async with async_session_maker() as session:
        statement = select(User)
        result = await session.execute(statement)
        users = result.scalars().all()
        for user in users:
            print(f"ID: {user.id}, Email: {user.email}, Role: {user.role}")

if __name__ == "__main__":
    asyncio.run(list_users())
