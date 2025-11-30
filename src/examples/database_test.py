from database import repository
from database.session import init_models, AsyncSessionLocal


async def main():
    await init_models()
    async with AsyncSessionLocal() as session:
        positions = await repository.get_open_positions(session)
        print(positions)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
