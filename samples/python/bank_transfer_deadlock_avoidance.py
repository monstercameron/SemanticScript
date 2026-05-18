from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time


# Deadlock-avoidance baseline: every transfer locks accounts in stable order.
# This exercises shared mutable state, lock ordering, and invariant checking.
class Account:
    def __init__(self, account_id, balance_cents):
        self.account_id = account_id
        self.balance_cents = balance_cents
        self.lock = Lock()


def lock_pair(left_account, right_account):
    accounts = sorted([left_account, right_account], key=lambda account: account.account_id)
    accounts[0].lock.acquire()
    accounts[1].lock.acquire()
    return accounts


def unlock_pair(locked_accounts):
    for account in reversed(locked_accounts):
        account.lock.release()


def transfer_money(transfer_id, from_account, to_account, amount_cents):
    locked_accounts = lock_pair(from_account, to_account)

    try:
        # Delay inside the critical section makes lock ordering matter.
        time.sleep(0.002)

        if from_account.balance_cents < amount_cents:
            return {
                "transfer_id": transfer_id,
                "status": "rejected",
                "reason": "insufficient_funds",
            }

        from_account.balance_cents -= amount_cents
        to_account.balance_cents += amount_cents

        return {
            "transfer_id": transfer_id,
            "status": "applied",
            "reason": "",
        }
    finally:
        unlock_pair(locked_accounts)


def main():
    accounts = {
        "checking": Account("checking", 100_00),
        "savings": Account("savings", 250_00),
        "tax": Account("tax", 50_00),
    }

    initial_total_cents = sum(account.balance_cents for account in accounts.values())

    transfers = [
        (1, accounts["checking"], accounts["savings"], 25_00),
        (2, accounts["savings"], accounts["tax"], 40_00),
        (3, accounts["tax"], accounts["checking"], 10_00),
        (4, accounts["checking"], accounts["tax"], 120_00),
        (5, accounts["savings"], accounts["checking"], 30_00),
    ]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(transfer_money, transfer_id, from_account, to_account, amount_cents)
            for transfer_id, from_account, to_account, amount_cents in transfers
        ]
        results = [future.result() for future in futures]

    final_total_cents = sum(account.balance_cents for account in accounts.values())

    print("Bank Transfer Deadlock Avoidance")
    print("===============================")

    for result in sorted(results, key=lambda item: item["transfer_id"]):
        print("transfer={transfer_id} status={status} reason={reason}".format(**result))

    print("balances:")
    for account_id in sorted(accounts):
        print("  {}={}".format(account_id, accounts[account_id].balance_cents))

    print("initialTotal={}".format(initial_total_cents))
    print("finalTotal={}".format(final_total_cents))
    print("invariantTotalPreserved={}".format(initial_total_cents == final_total_cents))


if __name__ == "__main__":
    main()
