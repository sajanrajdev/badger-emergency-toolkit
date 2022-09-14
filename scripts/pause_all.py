from brownie import interface, accounts
from helpers.utils import connect_account
from helpers.addresses import r
from rich.console import Console
from tqdm import tqdm
import click
from brownie.network import gas_price
from brownie.network.gas.strategies import ExponentialScalingStrategy

C = Console()

REGISTRY = interface.IBadgerRegistryV2(r.registry_v2)
GUARDIAN = interface.IWarRoomGatedProxy(REGISTRY.get("guardian"))
YEARN_VAULT = r.yearn_vaults.byvWBTC

VAULT_STATUS = [0, 1, 2, 3]

def main():
    # Get caller account
    dev = connect_account()

    # Set exponential gas strategy parameters
    custom_gas = click.prompt("Set custom gas strategy? (default: Exponential from 100 gwei to 200 gwei with 30s interval)", type=click.Choice(["y", "n"]))
    if custom_gas == "y":
        confirm = "n"
        while confirm == "n":
            initial = input("Initial gas price in gwei:")
            max = input("Max gas price in gwei:")
            interval = input("Interval in seconds:")
            confirm = click.prompt(f"Exponential gas strategy from {initial} gwei to {max} with {interval}s, confirm?", type=click.Choice(["y", "n"]))
        gas_price(ExponentialScalingStrategy(f"{initial} gwei", f"{max} gwei", interval))
    else:
        gas_price(ExponentialScalingStrategy("100 gwei", "200 gwei", 30))

    # 1. Pause GAC (Doing it first as it will quickly pause most of the vaults)
    GUARDIAN.pause(REGISTRY.get("globalAccessControl"), {"from": dev})

    # 2. Fetch all vaults from the Registry (V1, V1.5) for all status (deprecated, exp, guarded, open)
    C.print("[cyan]Fetching vaults and strategies from Registry...[/cyan]")
    vaults_v1 = []
    for status in tqdm(VAULT_STATUS):
        vaults_v1 += extract(REGISTRY.getFilteredProductionVaults("v1", status))

    vaults_v1_5 = []
    for status in tqdm(VAULT_STATUS):
        vaults_v1_5 += extract(REGISTRY.getFilteredProductionVaults("v1.5", status))

    # 3. Fetch all strategies from the vaults and identify the vaults that can't be paused via GAC
    vaults_non_gac = []
    strategies = []
    for address in vaults_v1:
        vault = interface.ISettV4h(address)
        # Yearn vault doesn't contain controller/strategy
        if address != YEARN_VAULT:
            controller = interface.IController(vault.controller())
            strategies.append(controller.strategies(vault.token()))
        # Check if GAC variable exists on vault
        try:
            vault.GAC()
        except:
            vaults_non_gac.append(vault)

    for address in vaults_v1_5:
        vault = interface.ITheVault(address)
        strategies.append(vault.strategy())
        vaults_non_gac.append(vault) # V1.5 vaults don't have GAC

    # 4. Sequentially pause all non GAC vaults
    for vault in vaults_non_gac:
        try:
            GUARDIAN.pause(vault.address, {"from": dev})
        # Some vaults are not pausable    
        except:
            C.print(f"[red]Vault {vault.symbol()} wasn't paused[/red]")

    # 5. Sequentially pause all strats
    for strat in strategies:
        try:
            GUARDIAN.pause(strat, {"from": dev})
        except:
            C.print(f"[red]Strategy with address {strat} wasn't paused[/red]")

    # 6. Pause badgerTree
    try:
        GUARDIAN.pause(REGISTRY.get("badgerTree"), {"from": dev})
    except:
        C.print(f"[red]Badger Tree wasn't paused[/red]")

    # 7. Pause ibBTC Core
    try:
        GUARDIAN.pause((interface.IibBTC(REGISTRY.get("ibBTC"))).core(), {"from": dev})
    except:
        C.print(f"[red]IbBTC's core wasn't paused[/red]")



def extract(lst):
    return [item[0] for item in lst]