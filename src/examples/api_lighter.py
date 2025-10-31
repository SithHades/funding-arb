import asyncio
from src.dex_adapters.lighter_adapter import LighterAdapter


async def positions_printer(adapter: LighterAdapter):
    positions = await adapter.list_positions()
    print("Current Positions:")
    print(positions)
    print("=" * 40)


async def open_position(adapter: LighterAdapter):
    print("Opening ETH Position for 40 USDC...")
    result = await adapter.open_position(
        "BTC", "SHORT", 40.0, leverage=1.0, slippage=-0.05
    )
    print(result)


async def wait(duration: int = 20):
    print(f"Waiting for {duration} seconds before closing position...")
    await asyncio.sleep(duration)
    print("=" * 40)


async def close(adapter: LighterAdapter):
    print("Closing ETH Position...")
    result = await adapter.close_position("BTC")
    print(result)


async def main():
    adapter = LighterAdapter()
    try:
        await positions_printer(adapter)
        await open_position(adapter)
        await wait(20)
        await close(adapter)

    except Exception as e:
        raise e
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
