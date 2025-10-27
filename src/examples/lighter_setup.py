import asyncio
import logging
import os

# (no blocking sleep; use asyncio.sleep)
import eth_account
import lighter
import dotenv

dotenv.load_dotenv()

logging.basicConfig(level=logging.DEBUG)

# this is a dummy private key which is registered on Testnet.
# It serves as a good example
BASE_URL = "https://testnet.zklighter.elliot.ai"
ETH_PRIVATE_KEY = os.environ.get("ETHEREUM_PRIVATE_KEY")
ETH_ADDRESS = os.environ.get("ETHEREUM_ADDRESS")
API_WALLET_PK = os.environ.get("LIGHTER_API_WALLET_PK")
API_WALLET_PUB_KEY = os.environ.get("LIGHTER_API_WALLET_PUB_KEY")
API_KEY_INDEX = 2


async def main():
    # verify that the account exists & fetch account index
    api_client = lighter.ApiClient(configuration=lighter.Configuration(host=BASE_URL))
    eth_acc = eth_account.Account.from_key(ETH_PRIVATE_KEY)
    eth_address = eth_acc.address

    try:
        response = await lighter.AccountApi(api_client).accounts_by_l1_address(
            l1_address=eth_address
        )
    except lighter.ApiException as e:
        if (
            getattr(e, "data", None)
            and getattr(e.data, "message", None) == "account not found"
        ):
            print(f"error: account not found for {eth_address}")
            return
        else:
            raise e

    if len(response.sub_accounts) > 1:
        for sub_account in response.sub_accounts:
            print(f"found accountIndex: {sub_account.index}")

        print("multiple accounts found, using the first one")
        account_index = response.sub_accounts[0].index
    else:
        account_index = response.sub_accounts[0].index

    # create a private/public key pair for the new API key
    # pass any string to be used as seed for create_api_key like
    # create_api_key("Hello world random seed to make things more secure")

    private_key, public_key, err = lighter.create_api_key()
    if err is not None:
        raise Exception(err)

    tx_client = lighter.SignerClient(
        url=BASE_URL,
        private_key=private_key,
        account_index=account_index,
        api_key_index=API_KEY_INDEX,
    )

    # change the API key
    response, err = await tx_client.change_api_key(
        eth_private_key=ETH_PRIVATE_KEY,
        new_pubkey=public_key,
    )
    if err is not None:
        raise Exception(err)

    # wait some time so that we receive the new API key in the response
    await asyncio.sleep(10)

    # check that the API key changed on the server
    err = tx_client.check_client()
    if err is not None:
        raise Exception(err)

    print(
        f"""
BASE_URL = '{BASE_URL}'
API_KEY_PRIVATE_KEY = '{private_key}'
ACCOUNT_INDEX = {account_index}
API_KEY_INDEX = {API_KEY_INDEX}
    """
    )

    # ensure clients are closed even on errors
    try:
        await tx_client.close()
    except Exception:
        pass
    try:
        await api_client.close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
