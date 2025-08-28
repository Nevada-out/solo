# solo-bridge-event-listener

This repository contains a Python script that simulates the core component of a cross-chain bridge: an event listener. This component is responsible for monitoring a 'source' blockchain for specific events (e.g., asset deposits) and relaying them as transactions to a 'destination' blockchain (e.g., to mint a wrapped asset).

The script is designed with a robust architecture, featuring clear separation of concerns, state management, and error handling, making it a good representation of a real-world, production-grade service in a decentralized ecosystem.

## Concept

A cross-chain bridge allows users to transfer assets or data from one blockchain to another. A common implementation pattern is "lock-and-mint":

1.  A user deposits an asset (e.g., ETH) into a smart contract on the source chain (e.g., Ethereum).
2.  This contract locks the asset and emits a `DepositInitiated` event containing details like the recipient's address on the destination chain and the amount.
3.  Off-chain services, called listeners or relayers, constantly monitor the source chain for these events.
4.  Upon detecting a new `DepositInitiated` event, the listener validates it and submits a transaction to a smart contract on the destination chain (e.g., Polygon).
5.  This destination contract verifies the listener's message and mints a corresponding wrapped asset (e.g., WETH) to the recipient.

This script simulates steps 3, 4, and 5 of this process.

## Code Architecture

The script is architected into several distinct classes, each with a specific responsibility. This modular design enhances readability, testability, and maintainability.

```
+-----------------------+
|      Main Loop        |
|   (if __name__ == '__main__')   |
+-----------+-----------+
            |
            v
+-----------------------+
|    EventProcessor     | (Core Orchestrator)
+-----------+-----------+
            |           |
  (uses)    |           | (uses)
            v           v
+-----------------------+   +-----------------------+
| BridgeContractHandler |   | BridgeContractHandler |
|   (Source Chain)      |   |  (Destination Chain)  |
+-----------+-----------+   +-----------+-----------+
            |           |           |
            v           |           v
+-----------------------+   |   +-----------------------+
| MockBlockchainConnector|  |   | MockBlockchainConnector|
+-----------------------+   |   +-----------------------+
                            |
                            v
                      +-----------+
                      |  StateDB  |
                      +-----------+
```

*   **`MockBlockchainConnector`**: Simulates a connection to a blockchain node's RPC endpoint. It mimics the behavior of `web3.py` for fetching blocks and logs but generates mock data. This allows the script to run without needing access to actual blockchain nodes.

*   **`StateDB`**: Provides a simple, file-based persistence layer (`state.json`). It keeps track of the last block number processed and the nonces of completed transactions. This is crucial to ensure that the listener can resume from where it left off after a restart and does not process the same event twice.

*   **`BridgeContractHandler`**: An abstraction layer for interacting with a specific smart contract. It uses a `BlockchainConnector` to fetch and decode event logs from the source chain or to submit minting transactions to the destination chain.

*   **`EventProcessor`**: The heart of the application. It contains the main processing loop. Its responsibilities include:
    *   Determining which blocks to scan.
    *   Orchestrating the fetching of events via the `BridgeContractHandler`.
    *   Validating each event (e.g., checking against the `StateDB` and target chain ID).
    *   Triggering the minting transaction on the destination chain.
    *   Confirming the transaction's success and updating the state.

## How it Works

1.  **Initialization**: The script starts by setting up connectors for both the source and destination chains, initializing the `StateDB`, and creating the main `EventProcessor`.

2.  **Main Loop**: The `EventProcessor` enters an infinite loop.

3.  **Block Scanning**: In each iteration, it queries the `StateDB` for the last processed block number and the `MockBlockchainConnector` for the current latest block number on the source chain.

4.  **Event Fetching**: It requests all `DepositInitiated` events within the calculated block range (`last_processed_block + 1` to `latest_block`). The `MockBlockchainConnector` simulates the appearance of a new event every few blocks.

5.  **Event Processing**: For each fetched event, it performs a series of checks:
    *   **Filtering**: Is the event's destination chain ID the one this listener is configured to handle?
    *   **Deduplication**: Has the event's unique `nonce` already been processed? (checked against `StateDB`).

6.  **Transaction Simulation**: If the event is valid and new, the processor instructs the destination `BridgeContractHandler` to `execute_mint`. This simulates creating, signing, and sending a transaction.

7.  **Confirmation**: The processor then simulates waiting for the transaction to be mined by calling `get_transaction_receipt`. 

8.  **State Update**: If the transaction was successful (`status == 1`), the processor tells the `StateDB` to record the event's `nonce` as completed. Finally, after scanning a batch of blocks, it updates the `last_processed_block` in the `StateDB`.

9.  **Error Handling**: If a transaction fails or an RPC error occurs, the script logs the error. The `last_processed_block` is *not* updated, ensuring that the script will retry processing the failed event in the next loop iteration.

## Usage Example

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd solo
    ```

2.  **Install dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Configure Environment (Optional):**
    The script uses default mock values. You can override them by creating a `.env` file in the root directory:
    ```
    # .env file
    SOURCE_CHAIN_RPC="http://127.0.0.1:8545"
    DEST_CHAIN_RPC="http://127.0.0.1:8546"
    SOURCE_CONTRACT_ADDRESS="0x..."
    DEST_CONTRACT_ADDRESS="0x..."
    ```

4.  **Run the script:**
    ```bash
    python script.py
    ```

5.  **Expected Output:**
    You will see logs in your console and in a `bridge_listener.log` file. The script will periodically report that it is scanning blocks. Every 5 blocks (by default in the simulation), it will find and process a new event.

    ```
    2023-10-27 10:30:00,123 - CrossChainBridgeListener - INFO - --- Cross-Chain Bridge Event Listener starting ---
    2023-10-27 10:30:00,124 - CrossChainBridgeListener - INFO - No new blocks to process. Current head: 0. Waiting...
    ...
    2023-10-27 10:30:40,500 - CrossChainBridgeListener - INFO - [SourceChain] Fetching events for contract 0x... from block 1 to 5.
    2023-10-27 10:30:40,501 - CrossChainBridgeListener - INFO - [SourceChain] Found 1 new mock event in block 5.
    2023-10-27 10:30:40,502 - CrossChainBridgeListener - INFO - Found 1 new deposit events between blocks 1 and 5.
    2023-10-27 10:30:40,503 - CrossChainBridgeListener - INFO - Processing event (Nonce: 5, TX: 0x...).
    2023-10-27 10:30:40,504 - CrossChainBridgeListener - WARNING - Could not fetch gas price from oracle: ... Using default value.
    2023-10-27 10:30:40,505 - CrossChainBridgeListener - INFO - [DestinationChain] Preparing mint transaction for nonce 5. Recipient: 0x..., Amount: 1000000000000000000
    2023-10-27 10:30:40,506 - CrossChainBridgeListener - INFO - [DestinationChain] Simulating transaction submission. TX_HASH: 0x...
    2023-10-27 10:30:41,507 - CrossChainBridgeListener - INFO - [DestinationChain] Fetching receipt for 0x...
    2023-10-27 10:30:41,508 - CrossChainBridgeListener - INFO - Successfully processed event (Nonce: 5, TX: 0x...). Mint TX: 0x...
    2023-10-27 10:30:41,509 - CrossChainBridgeListener - INFO - Nonce 5 marked as processed.
    2023-10-27 10:30:41,510 - CrossChainBridgeListener - DEBUG - Successfully scanned up to block 5. State updated.
    ```
