import asyncio
from src.dex_adapters import ExtendedAdapter


async def main():
    adapter = ExtendedAdapter()
    balance = await adapter.get_balance()
    print(f"ExtendedAdapter balance: {balance}")
    positions = await adapter.list_positions(token=None)
    print(f"ExtendedAdapter positions: {positions}")
    await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
