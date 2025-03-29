import os
import time
import logging
from enum import Enum
from typing import List, Dict, Any, Optional

import requests
from web3 import Web3
from web3.exceptions import BlockNotFound
from web3.contract import Contract
from dotenv import load_dotenv

# --- Configuration & Setup ---

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Constants & Mock Data ---

# This is a simplified ABI for a generic ERC20-like token locking contract.
# In a real scenario, this would be the actual ABI of the deployed bridge contract.
SOURCE_CHAIN_BRIDGE_ABI = '''
[
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "address",
                "name": "token",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "uint256",
                "name": "destinationChainId",
                "type": "uint256"
            }
        ],
        "name": "TokensLocked",
        "type": "event"
    }
]
'''

# ABI for the destination chain contract to mint tokens.
DESTINATION_CHAIN_BRIDGE_ABI = '''
[
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "recipient",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            },
            {
                "internalType": "bytes32",
                "name": "sourceTxHash",
                "type": "bytes32"
            }
        ],
        "name": "mintBridgedTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
'''

# Number of block confirmations required on the source chain before relaying.
REQUIRED_CONFIRMATIONS = 12

# --- Enums and Data Classes ---

class TransactionStatus(Enum):
    """Represents the lifecycle of a cross-chain transaction."""
    INITIATED = 'INITIATED'                  # Event detected on source chain
    CONFIRMED_SOURCE = 'CONFIRMED_SOURCE'    # Reached required confirmations
    RELAY_PENDING = 'RELAY_PENDING'          # Ready to be sent to destination chain
    RELAYED = 'RELAYED'                      # Transaction sent to destination chain
    COMPLETED = 'COMPLETED'                  # Successfully processed on destination chain
    FAILED = 'FAILED'                        # An error occurred

class CrossChainTransaction:
    """A data class to hold the state and details of a single cross-chain transaction."""

    def __init__(self, tx_hash: str, event_data: Dict[str, Any]):
        self.tx_hash = tx_hash
        self.status = TransactionStatus.INITIATED
        self.sender = event_data['args']['sender']
        self.token = event_data['args']['token']
        self.amount = event_data['args']['amount']
        self.destination_chain_id = event_data['args']['destinationChainId']
        self.source_block_number = event_data['blockNumber']
        self.destination_tx_hash: Optional[str] = None
        self.failure_reason: Optional[str] = None
        self.attempts = 0
        self.created_at = time.time()

    def __repr__(self) -> str:
        return f"CrossChainTransaction(hash={self.tx_hash}, status={self.status.value}, amount={self.amount})"

# --- Core Components ---

class BlockchainConnector:
    """Handles connection and interaction with a single blockchain node."""

    def __init__(self, chain_name: str, rpc_url: str):
        self.logger = logging.getLogger(f"Connector:{chain_name}")
        self.chain_name = chain_name
        try:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to {chain_name} RPC at {rpc_url}")
            self.logger.info(f"Successfully connected to {chain_name}. Chain ID: {self.w3.eth.chain_id}")
        except Exception as e:
            self.logger.error(f"Error connecting to {chain_name}: {e}")
            raise

    def get_latest_block_number(self) -> int:
        """Fetches the most recent block number from the blockchain."""
        try:
            return self.w3.eth.block_number
        except Exception as e:
            self.logger.error(f"Failed to get latest block number: {e}")
            # In a real app, you might want to return a cached value or retry.
            return 0

    def get_contract(self, address: str, abi: str) -> Contract:
        """Returns a Web3 contract instance."""
        checksum_address = Web3.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum_address, abi=abi)

class EventScanner:
    """Scans a blockchain for specific contract events within a block range."""

    def __init__(self, connector: BlockchainConnector, contract: Contract, event_name: str):
        self.logger = logging.getLogger(f"EventScanner:{connector.chain_name}")
        self.connector = connector
        self.contract = contract
        self.event_name = event_name
        self.event_filter = self.contract.events[event_name].create_filter(fromBlock='latest')

    def scan_for_events(self, from_block: int, to_block: int) -> List[Dict[str, Any]]:
        """Scans a given block range for new events."""
        if from_block > to_block:
            return []

        self.logger.info(f"Scanning for '{self.event_name}' events from block {from_block} to {to_block}.")
        try:
            # Use a filter for efficiency.
            event_filter = self.contract.events[self.event_name].create_filter(
                fromBlock=from_block,
                toBlock=to_block
            )
            events = event_filter.get_all_entries()
            if events:
                self.logger.info(f"Found {len(events)} new '{self.event_name}' events.")
            return events
        except BlockNotFound:
            self.logger.warning(f"Block range [{from_block}-{to_block}] not found. Chain might be syncing. Retrying later.")
            return []
        except Exception as e:
            self.logger.error(f"An error occurred while scanning for events: {e}")
            return []

class BridgeRelayer:
    """Orchestrates the cross-chain bridging process.

    This component listens for events on the source chain, validates them,
    and simulates relaying them to the destination chain.
    """

    def __init__(self, source_connector: BlockchainConnector, dest_connector: BlockchainConnector, 
                 source_contract_address: str, dest_contract_address: str):
        self.logger = logging.getLogger("BridgeRelayer")
        self.source_connector = source_connector
        self.dest_connector = dest_connector
        
        self.source_contract = self.source_connector.get_contract(source_contract_address, SOURCE_CHAIN_BRIDGE_ABI)
        self.dest_contract = self.dest_connector.get_contract(dest_contract_address, DESTINATION_CHAIN_BRIDGE_ABI)
        
        self.event_scanner = EventScanner(self.source_connector, self.source_contract, 'TokensLocked')

        self.active_transactions: Dict[str, CrossChainTransaction] = {}
        self.last_scanned_block = self.source_connector.get_latest_block_number() - 1 # Start from the previous block

    def process_new_events(self):
        """Scans for and processes new 'TokensLocked' events."""
        latest_block = self.source_connector.get_latest_block_number()
        if latest_block <= self.last_scanned_block:
            return # No new blocks to scan
        
        # To avoid scanning too large a range at once.
        to_block = min(latest_block, self.last_scanned_block + 100)

        events = self.event_scanner.scan_for_events(self.last_scanned_block + 1, to_block)
        for event in events:
            tx_hash = event['transactionHash'].hex()
            if tx_hash not in self.active_transactions:
                self.logger.info(f"New transaction detected: {tx_hash}")
                transaction = CrossChainTransaction(tx_hash, event)
                self.active_transactions[tx_hash] = transaction
        
        self.last_scanned_block = to_block

    def process_active_transactions(self):
        """Processes all non-completed transactions through the state machine."""
        if not self.active_transactions:
            self.logger.info("No active transactions to process.")
            return
        
        latest_block = self.source_connector.get_latest_block_number()

        for tx_hash, tx in list(self.active_transactions.items()):
            self.logger.debug(f"Processing transaction {tx_hash} with status {tx.status}")

            if tx.status == TransactionStatus.INITIATED:
                self._handle_initiated(tx, latest_block)
            
            elif tx.status == TransactionStatus.CONFIRMED_SOURCE:
                self._handle_confirmed(tx)
            
            elif tx.status == TransactionStatus.RELAY_PENDING:
                self._handle_relay(tx)
            
            # Clean up completed or old failed transactions
            if tx.status in [TransactionStatus.COMPLETED, TransactionStatus.FAILED]:
                if (time.time() - tx.created_at) > 3600: # Remove after 1 hour
                    self.logger.info(f"Removing completed/failed transaction: {tx_hash}")
                    del self.active_transactions[tx_hash]

    def _handle_initiated(self, tx: CrossChainTransaction, latest_block: int):
        """Check for enough confirmations on the source chain."""
        confirmations = latest_block - tx.source_block_number
        if confirmations >= REQUIRED_CONFIRMATIONS:
            self.logger.info(f"Transaction {tx.tx_hash} has reached {confirmations} confirmations. Updating status.")
            tx.status = TransactionStatus.CONFIRMED_SOURCE
        else:
            self.logger.debug(f"Transaction {tx.tx_hash} waiting for confirmations ({confirmations}/{REQUIRED_CONFIRMATIONS}).")

    def _handle_confirmed(self, tx: CrossChainTransaction):
        """Simulate getting a signature from an oracle service."""
        self.logger.info(f"Simulating call to oracle/validator network for {tx.tx_hash}...")
        try:
            # This simulates calling an external service (e.g., a network of validators)
            # that would sign the transaction data, authorizing the mint on the destination chain.
            # We use `requests` to demonstrate interaction with an external HTTP service.
            response = requests.get('https://api.mocki.io/v2/511c64b5/signature', timeout=5)
            if response.status_code == 200:
                self.logger.info(f"Successfully obtained mock signature for {tx.tx_hash}")
                tx.status = TransactionStatus.RELAY_PENDING
            else:
                self.logger.warning(f"Oracle service returned status {response.status_code} for {tx.tx_hash}. Retrying later.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to contact oracle service for {tx.tx_hash}: {e}. Retrying later.")

    def _handle_relay(self, tx: CrossChainTransaction):
        """Simulate submitting the transaction to the destination chain."""
        self.logger.info(f"Relaying transaction {tx.tx_hash} to destination chain {tx.destination_chain_id}.")
        tx.attempts += 1
        try:
            # In a real relayer, you would build, sign, and send a transaction here.
            # We are simply simulating this action.
            self.logger.info(f"SIMULATING: Calling 'mintBridgedTokens' on destination contract for user {tx.sender} with amount {tx.amount}")
            # Mocking a successful transaction submission.
            mock_dest_tx_hash = Web3.keccak(text=f"{tx.tx_hash}-{tx.attempts}").hex()
            tx.destination_tx_hash = mock_dest_tx_hash
            tx.status = TransactionStatus.RELAYED
            self.logger.info(f"Transaction {tx.tx_hash} successfully relayed to destination chain. Destination Tx Hash (mock): {tx.destination_tx_hash}")
            
            # For simulation purposes, we'll immediately mark it as completed.
            # In reality, you'd wait for this destination tx to be mined and confirmed.
            tx.status = TransactionStatus.COMPLETED
            self.logger.info(f"BRIDGE COMPLETED for {tx.tx_hash}")

        except Exception as e:
            self.logger.error(f"Failed to relay transaction {tx.tx_hash}: {e}")
            tx.failure_reason = str(e)
            if tx.attempts > 5:
                self.logger.error(f"Transaction {tx.tx_hash} failed after multiple attempts. Marking as FAILED.")
                tx.status = TransactionStatus.FAILED

    def run_simulation_cycle(self):
        """Executes one full cycle of the relayer's logic."""
        self.logger.info("--- Starting new simulation cycle ---")
        self.process_new_events()
        self.process_active_transactions()
        self.logger.info(f"--- Cycle finished. Active transactions: {len(self.active_transactions)} ---")
        # Print a summary of active transactions
        for tx_hash, tx in self.active_transactions.items():
            print(f"  - Hash: {tx_hash[:10]}... | Status: {tx.status.value} | Amount: {tx.amount}")

# --- Main Execution ---

def main():
    """Main function to set up and run the relayer simulation."""
    logger = logging.getLogger("main")
    logger.info("Initializing Debuy Cross-Chain Bridge Relayer Simulation...")

    # Load configuration from environment variables
    source_rpc_url = os.getenv('SOURCE_CHAIN_RPC_URL')
    dest_rpc_url = os.getenv('DESTINATION_CHAIN_RPC_URL')
    source_contract_addr = os.getenv('SOURCE_BRIDGE_CONTRACT_ADDRESS')
    dest_contract_addr = os.getenv('DESTINATION_BRIDGE_CONTRACT_ADDRESS')

    if not all([source_rpc_url, dest_rpc_url, source_contract_addr, dest_contract_addr]):
        logger.error("Missing required environment variables. Please check your .env file.")
        logger.error("Required: SOURCE_CHAIN_RPC_URL, DESTINATION_CHAIN_RPC_URL, SOURCE_BRIDGE_CONTRACT_ADDRESS, DESTINATION_BRIDGE_CONTRACT_ADDRESS")
        return

    try:
        # Setup connectors
        # NOTE: For this simulation to run, you need access to two Ethereum-compatible JSON-RPC endpoints.
        # You can use a service like Infura/Alchemy or run local nodes (e.g., using Ganache/Anvil).
        source_connector = BlockchainConnector("SourceChain", source_rpc_url)
        dest_connector = BlockchainConnector("DestinationChain", dest_rpc_url)

        # Initialize the relayer
        relayer = BridgeRelayer(
            source_connector=source_connector,
            dest_connector=dest_connector,
            source_contract_address=source_contract_addr,
            dest_contract_address=dest_contract_addr
        )

        # Run the simulation loop
        logger.info("Starting simulation loop. Press Ctrl+C to exit.")
        cycle_count = 0
        while True:
            cycle_count += 1
            logger.info(f"==================== Cycle #{cycle_count} ====================")
            relayer.run_simulation_cycle()
            
            # Wait before the next cycle to avoid spamming RPC endpoints
            time.sleep(15) 

    except ConnectionError as e:
        logger.error(f"A blockchain connection error occurred: {e}")
    except KeyboardInterrupt:
        logger.info("Simulation stopped by user.")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    # To run this script:
    # 1. Create a `.env` file in the same directory.
    # 2. Add the following lines, replacing with your actual data:
    #    SOURCE_CHAIN_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID
    #    DESTINATION_CHAIN_RPC_URL=https://goerli.infura.io/v3/YOUR_INFURA_PROJECT_ID
    #    SOURCE_BRIDGE_CONTRACT_ADDRESS=0xYourSourceContractAddress
    #    DESTINATION_BRIDGE_CONTRACT_ADDRESS=0xYourDestinationContractAddress
    # 3. Run `python script.py`
    main()
