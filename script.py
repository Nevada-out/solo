import time
import logging
import json
import os
from typing import Dict, Any, List, Optional, Tuple
from collections import namedtuple
from uuid import uuid4

import requests
from web3 import Web3
from web3.types import LogReceipt
from dotenv import load_dotenv

# --- Configuration & Setup ---

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bridge_listener.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('CrossChainBridgeListener')

# --- Mocks & Simulation Data ---

# In a real scenario, this would be the actual ABI of the smart contract.
# We define a minimal version for simulation purposes.
BRIDGE_CONTRACT_ABI = json.loads('''
[
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "name": "sender", "type": "address"},
            {"indexed": true, "name": "recipient", "type": "address"},
            {"indexed": false, "name": "amount", "type": "uint256"},
            {"indexed": false, "name": "destinationChainId", "type": "uint256"},
            {"indexed": false, "name": "nonce", "type": "uint64"}
        ],
        "name": "DepositInitiated",
        "type": "event"
    }
]
''')

# A simple named tuple to represent a structured event for easier access.
DepositEvent = namedtuple('DepositEvent', ['sender', 'recipient', 'amount', 'destinationChainId', 'nonce', 'tx_hash', 'log_index'])

class MockBlockchainConnector:
    """
    Mocks the connection to a blockchain node (e.g., via Web3.py).
    This class simulates fetching blocks and event logs without a real RPC connection,
    making the script self-contained and testable.
    """
    def __init__(self, chain_name: str, rpc_url: str):
        self.chain_name = chain_name
        self.rpc_url = rpc_url
        self.current_block = 0
        self.w3 = Web3() # Using Web3 for utilities like checksum addresses
        logger.info(f"MockConnector for '{self.chain_name}' initialized at '{self.rpc_url}'.")

    def get_latest_block_number(self) -> int:
        """Simulates fetching the latest block number."""
        # Increment block number slowly to simulate blockchain progression.
        self.current_block += 1
        logger.debug(f"[{self.chain_name}] New block: {self.current_block}")
        return self.current_block

    def get_events(self, contract_address: str, from_block: int, to_block: int) -> List[LogReceipt]:
        """
        Simulates fetching 'DepositInitiated' event logs from a range of blocks.
        In a real implementation, this would use `web3.eth.get_logs()`.
        """
        if from_block > to_block:
            return []

        logger.info(f"[{self.chain_name}] Fetching events for contract {contract_address} from block {from_block} to {to_block}.")
        
        # Simulate a new event appearing every few blocks.
        if self.current_block % 5 == 0:
            # Generate a realistic-looking mock event log.
            mock_event: LogReceipt = {
                'address': Web3.to_checksum_address(contract_address),
                'topics': [
                    # A realistic event signature hash for DepositInitiated(...)
                    '0x' + 'a' * 64, 
                    '0x' + 'b' * 64, # Mock sender
                    '0x' + 'c' * 64  # Mock recipient
                ],
                'data': '0x' + f'{1000000000000000000:064x}' + f'{97:064x}' + f'{self.current_block:064x}', # amount, destinationChainId, nonce
                'blockNumber': self.current_block,
                'transactionHash': f'0x{uuid4().hex}',
                'transactionIndex': 0,
                'blockHash': f'0x{uuid4().hex}',
                'logIndex': 0,
                'removed': False
            }
            logger.info(f"[{self.chain_name}] Found 1 new mock event in block {self.current_block}.")
            return [mock_event]
        
        return []

    def send_raw_transaction(self, raw_tx: str) -> str:
        """Simulates sending a signed transaction to the network."""
        tx_hash = f'0x{uuid4().hex}'
        logger.info(f"[{self.chain_name}] Simulating transaction submission. TX_HASH: {tx_hash}")
        # Simulate a short delay for transaction to be 'mined'.
        time.sleep(1)
        return tx_hash

    def get_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        """Simulates fetching a transaction receipt to confirm it was successful."""
        logger.info(f"[{self.chain_name}] Fetching receipt for {tx_hash}...")
        return {
            'status': 1, # 1 for success, 0 for failure
            'blockNumber': self.get_latest_block_number() + 1,
            'transactionHash': tx_hash
        }

class StateDB:
    """
    Manages the persistent state of the listener.
    This includes the last block processed and a list of completed transaction nonces
    to prevent double-spending or re-processing events.
    """
    def __init__(self, db_path: str = 'state.json'):
        self.db_path = db_path
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads state from a JSON file, or creates a default state if not found."""
        try:
            with open(self.db_path, 'r') as f:
                logger.info(f"Loading state from {self.db_path}")
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"State file not found or invalid. Initializing new state.")
            return {
                'last_processed_block': 0,
                'completed_nonces': []
            }

    def _save(self) -> None:
        """Saves the current state to the JSON file."""
        with open(self.db_path, 'w') as f:
            json.dump(self.state, f, indent=4)

    def get_last_processed_block(self) -> int:
        return self.state.get('last_processed_block', 0)

    def set_last_processed_block(self, block_number: int) -> None:
        self.state['last_processed_block'] = block_number
        self._save()

    def is_nonce_processed(self, nonce: int) -> bool:
        return nonce in self.state['completed_nonces']

    def mark_nonce_as_processed(self, nonce: int) -> None:
        if not self.is_nonce_processed(nonce):
            self.state['completed_nonces'].append(nonce)
            self.state['completed_nonces'].sort()
            self._save()
            logger.info(f"Nonce {nonce} marked as processed.")

class BridgeContractHandler:
    """
    An abstraction for interacting with the bridge smart contract on a specific chain.
    It uses a BlockchainConnector to communicate with the chain.
    """
    def __init__(self, connector: MockBlockchainConnector, contract_address: str):
        self.connector = connector
        # Use Web3.py's contract object for easy event decoding
        self.contract = Web3().eth.contract(address=Web3.to_checksum_address(contract_address), abi=BRIDGE_CONTRACT_ABI)
        self.address = contract_address
        logger.info(f"BridgeContractHandler initialized for contract {self.address} on chain '{self.connector.chain_name}'.")

    def get_deposit_events(self, from_block: int, to_block: int) -> List[DepositEvent]:
        """
        Fetches raw logs and decodes them into structured DepositEvent objects.
        """
        try:
            raw_logs = self.connector.get_events(self.address, from_block, to_block)
            decoded_events = []
            for log in raw_logs:
                # The Contract object can decode logs that match its ABI
                event_data = self.contract.events.DepositInitiated().process_log(log)
                decoded_events.append(
                    DepositEvent(
                        sender=event_data.args.sender,
                        recipient=event_data.args.recipient,
                        amount=event_data.args.amount,
                        destinationChainId=event_data.args.destinationChainId,
                        nonce=event_data.args.nonce,
                        tx_hash=event_data.transactionHash.hex(),
                        log_index=event_data.logIndex
                    )
                )
            return decoded_events
        except Exception as e:
            logger.error(f"[{self.connector.chain_name}] Failed to get or decode events: {e}")
            return []

    def execute_mint(self, event: DepositEvent) -> Optional[str]:
        """
        Constructs and sends a transaction to mint tokens on the destination chain.
        In a real scenario, this would involve signing a transaction with a private key.
        """
        logger.info(
            f"[{self.connector.chain_name}] Preparing mint transaction for nonce {event.nonce}. "
            f"Recipient: {event.recipient}, Amount: {event.amount}"
        )
        # In a real app, you'd use contract.functions.mint(...).build_transaction(...)
        # and then sign it with a private key.
        mock_raw_tx = f"signed_mint_tx_for_nonce_{event.nonce}"
        try:
            tx_hash = self.connector.send_raw_transaction(mock_raw_tx)
            return tx_hash
        except Exception as e:
            logger.error(f"[{self.connector.chain_name}] Mint transaction failed to send: {e}")
            return None

class EventProcessor:
    """
    The core orchestrator of the bridge listener.
    It contains the main loop that scans the source chain, processes events,
    and triggers actions on the destination chain.
    """
    def __init__(self, 
                 source_handler: BridgeContractHandler, 
                 dest_handler: BridgeContractHandler, 
                 state_db: StateDB,
                 target_chain_id: int):
        self.source_handler = source_handler
        self.dest_handler = dest_handler
        self.state_db = state_db
        self.target_chain_id = target_chain_id # The chain ID this listener is responsible for
        self.poll_interval_seconds = 10
        self.block_scan_range = 100 # Process up to 100 blocks at a time to not overload the RPC

    def _fetch_gas_price_from_oracle(self) -> float:
        """Uses the requests library to fetch external data, e.g., a gas price oracle."""
        try:
            # Using a public, free API for demonstration
            response = requests.get('https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey=YourApiKeyToken')
            response.raise_for_status()
            gas_data = response.json()
            propose_gas_price = float(gas_data['result']['ProposeGasPrice'])
            logger.info(f"Fetched external gas price: {propose_gas_price} Gwei")
            return propose_gas_price
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not fetch gas price from oracle: {e}. Using default value.")
            return 50.0  # Return a default value on failure

    def process_single_event(self, event: DepositEvent) -> bool:
        """
        Handles the logic for a single event, from validation to execution.
        Returns True if the event was processed successfully, False otherwise.
        """
        event_id = f"(Nonce: {event.nonce}, TX: {event.tx_hash[:10]}...)"
        logger.info(f"Processing event {event_id}")

        # 1. Validation: Check if the event is destined for our target chain.
        if event.destinationChainId != self.target_chain_id:
            logger.debug(f"Skipping event {event_id}: destination chain is {event.destinationChainId}, not {self.target_chain_id}.")
            return True # Mark as processed successfully to not retry it

        # 2. State Check: Prevent re-processing completed events.
        if self.state_db.is_nonce_processed(event.nonce):
            logger.warning(f"Skipping event {event_id}: nonce has already been processed.")
            return True
        
        # 3. Simulate fetching external data required for the transaction.
        self._fetch_gas_price_from_oracle()

        # 4. Execution: Submit the minting transaction on the destination chain.
        mint_tx_hash = self.dest_handler.execute_mint(event)
        if not mint_tx_hash:
            logger.error(f"Failed to submit mint transaction for event {event_id}. Will retry later.")
            return False

        # 5. Confirmation: Wait for the transaction to be mined.
        # In a real system, this would have a more robust loop with timeouts and retries.
        try:
            receipt = self.dest_handler.connector.get_transaction_receipt(mint_tx_hash)
            if receipt and receipt['status'] == 1:
                logger.info(f"Successfully processed event {event_id}. Mint TX: {mint_tx_hash}")
                # 6. State Update: Mark as complete only after successful confirmation.
                self.state_db.mark_nonce_as_processed(event.nonce)
                return True
            else:
                logger.error(f"Mint transaction {mint_tx_hash} for event {event_id} failed on-chain (receipt status 0).")
                return False
        except Exception as e:
            logger.error(f"Error confirming transaction {mint_tx_hash}: {e}. Will retry later.")
            return False

    def run(self) -> None:
        """The main execution loop of the listener."""
        logger.info("--- Cross-Chain Bridge Event Listener starting ---")
        while True:
            try:
                # Determine the range of blocks to scan
                last_processed_block = self.state_db.get_last_processed_block()
                latest_block = self.source_handler.connector.get_latest_block_number()

                from_block = last_processed_block + 1
                to_block = min(latest_block, from_block + self.block_scan_range)

                if from_block > latest_block:
                    logger.info(f"No new blocks to process. Current head: {latest_block}. Waiting...")
                    time.sleep(self.poll_interval_seconds)
                    continue

                # Fetch and process events
                events = self.source_handler.get_deposit_events(from_block, to_block)
                if events:
                    logger.info(f"Found {len(events)} new deposit events between blocks {from_block} and {to_block}.")
                    for event in sorted(events, key=lambda e: (e.nonce, e.log_index)): # Process in order
                        success = self.process_single_event(event)
                        if not success:
                            # If any event fails, stop processing this batch and retry from the same
                            # starting block in the next iteration. This ensures events are processed in order.
                            logger.error(f"Halting current batch due to processing failure. Will retry from block {from_block}.")
                            break
                
                # If all events in the range were processed successfully, update the state.
                self.state_db.set_last_processed_block(to_block)
                logger.debug(f"Successfully scanned up to block {to_block}. State updated.")

            except Exception as e:
                logger.critical(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            
            time.sleep(self.poll_interval_seconds)

if __name__ == '__main__':
    # --- Main Execution --- 
    # In a real deployment, these values would come from environment variables or a config file.
    SOURCE_CHAIN_RPC = os.getenv("SOURCE_CHAIN_RPC", "http://localhost:8545")
    DEST_CHAIN_RPC = os.getenv("DEST_CHAIN_RPC", "http://localhost:8546")
    SOURCE_CONTRACT_ADDRESS = os.getenv("SOURCE_CONTRACT_ADDRESS", "0x5FbDB2315678afecb367f032d93F642f64180aa3")
    DEST_CONTRACT_ADDRESS = os.getenv("DEST_CONTRACT_ADDRESS", "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512")
    DESTINATION_CHAIN_ID_TO_LISTEN_FOR = 97 # e.g., BSC Testnet

    # 1. Initialize the state database
    state_manager = StateDB(db_path='bridge_state.json')

    # 2. Initialize connectors and handlers for source and destination chains
    source_connector = MockBlockchainConnector("SourceChain", SOURCE_CHAIN_RPC)
    dest_connector = MockBlockchainConnector("DestinationChain", DEST_CHAIN_RPC)

    source_handler = BridgeContractHandler(source_connector, SOURCE_CONTRACT_ADDRESS)
    dest_handler = BridgeContractHandler(dest_connector, DEST_CONTRACT_ADDRESS)

    # 3. Initialize and run the main processor
    processor = EventProcessor(
        source_handler=source_handler,
        dest_handler=dest_handler,
        state_db=state_manager,
        target_chain_id=DESTINATION_CHAIN_ID_TO_LISTEN_FOR
    )

    processor.run()
