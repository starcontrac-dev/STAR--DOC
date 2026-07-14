
import asyncio
from sqlmodel import Session, select
from app.database import engine, async_session_maker
from app.models.availability import AvailableSlot
from datetime import date, time, timedelta, datetime

async def seed_availability():
    # Empezamos desde mañana
    start_date = date.today() + timedelta(days=1)
    # Generamos para 14 días
    days_to_generate = 14
    
    # Horarios: 9:00, 10:00, 11:00, 14:00, 15:00, 16:00
    times = [
        time(9, 0), time(10, 0), time(11, 0),
        time(14, 0), time(15, 0), time(16, 0)
    ]
    
    async with async_session_maker() as session:
        # Limpiar slots futuros para evitar duplicados si se corre varias veces
        # (Opcional, pero útil en dev)
        # statement = select(AvailableSlot).where(AvailableSlot.slot_date >= date.today())
        # result = await session.execute(statement)
        # for s in result.scalars().all():
        #     await session.delete(s)
        # await session.commit()

        count = 0
        for i in range(days_to_generate):
            current_date = start_date + timedelta(days=i)
            
            # Saltamos fines de semana
            if current_date.weekday() >= 5:
                continue
                
            for t in times:
                # Verificar si ya existe
                stmt = select(AvailableSlot).where(AvailableSlot.slot_date == current_date, AvailableSlot.slot_time == t)
                existing = await session.execute(stmt)
                if existing.scalars().first():
                    continue
                
                slot = AvailableSlot(
                    slot_date=current_date,
                    slot_time=t,
                    duration_minutes=60,
                    is_booked=False,
                    is_blocked=False
                )
                session.add(slot)
                count += 1
        
        await session.commit()
        print(f"✅ Se crearon {count} nuevos slots de disponibilidad para 2026.")

if __name__ == "__main__":
    asyncio.run(seed_availability())
