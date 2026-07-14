import asyncio
import sys
import os
import argparse

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import select
from app.database import async_session_maker
from app.models.user import User, UserRole

async def promote_user(email: str, role: str):
    async with async_session_maker() as session:
        statement = select(User).where(User.email == email)
        result = await session.execute(statement)
        user = result.scalars().first()
        
        if not user:
            print(f"User with email {email} not found.")
            return

        try:
            target_role = UserRole(role)
        except ValueError:
            print(f"Invalid role: {role}. Valid roles: {', '.join([r.value for r in UserRole])}")
            return

        user.role = target_role
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"User {email} promoted to {user.role}")

def main():
    parser = argparse.ArgumentParser(description="Promote a user to a specific role.")
    parser.add_argument("--email", required=True, help="Email of the user to promote")
    parser.add_argument("--role", default="admin", help="Role to assign (admin, user)")
    
    args = parser.parse_args()
    
    asyncio.run(promote_user(args.email, args.role))

if __name__ == "__main__":
    main()
