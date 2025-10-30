# Debuy: Cross-Chain Bridge Event listener & Relayer Simulation

This repository contains a Python-based simulation of a crucial backend component for a cross-chain bridge: an event listener and transaction relayer. It demonstrates the architectural patterns required to securely and reliably move information between two distinct blockchains.

The script is designed to be modular and robust, showcasing best practices such as state management, error handling, and interaction with external services.

## Concept

A cross-chain bridge allows users to transfer assets or data from a _source chain_ to a _destination chain_. The core mechanism of many bridges works as follows:

1.  A user locks their assets in a smart contract on the source chain. This action emits an event (e.g., `TokensLocked`).
    ```solidity
    // A simplified example of the event in the source chain's smart contract
    event TokensLocked(
        address indexed user,
        address indexed token,
        uint256 amount,
        bytes32 indexed destinationTxId
    );
    ```
2.  A network of off-chain listeners, known as relayers or validators, detects this event.
3.  After waiting for a certain number of block confirmations on the source chain (to prevent re-org attacks), the relayers reach a consensus.
4.  One of the relayers then submits a transaction to a smart contract on the destination chain to mint an equivalent amount of "wrapped" assets for the user.

This project simulates the off-chain **relayer** component (steps 2, 3, and 4). It connects to a source chain, scans for lock events, manages the transaction lifecycle, and simulates the final submission to the destination chain.

## Code Architecture

The script is architected with a clear separation of concerns, with distinct classes handling different responsibilities:

-   **`BlockchainConnector`**: A generic wrapper around the `web3.py` library. It manages the connection to a single blockchain's JSON-RPC endpoint and provides methods for querying chain data and interacting with contracts. An instance is created for both the source and destination chains.

-   **`EventScanner`**: Responsible for scanning a specific block range on a blockchain for a particular smart contract event. It uses the `BlockchainConnector` to perform its queries and efficiently filters the results.

-   **`CrossChainTransaction`**: A data class representing the state of a single bridging transaction. It tracks everything from the initial event data to its current status (e.g., `INITIATED`, `CONFIRMED_SOURCE`, `COMPLETED`, `FAILED`), transaction hashes, and other metadata.
    ```python
    # A simplified representation of the transaction data class
    from dataclasses import dataclass
    from enum import Enum

    class TxStatus(Enum):
        INITIATED = "INITIATED"
        CONFIRMED_SOURCE = "CONFIRMED_SOURCE"
        RELAY_PENDING = "RELAY_PENDING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    @dataclass
    class CrossChainTransaction:
        tx_hash_source: str
        status: TxStatus
        event_data: dict
        confirmations: int = 0
        # ... other relevant fields like destination tx hash, error messages, etc.
    ```

-   **`BridgeRelayer`**: The central orchestrator that integrates all other components and contains the main business logic for the bridging process:
    -   Initializes and manages the `EventScanner`.
    -   Maintains a dictionary of all `CrossChainTransaction` objects currently in flight.
    -   Implements the state machine for processing transactions from detection to completion.
    -   Handles logic for checking block confirmations.
    -   Simulates interaction with external services (like an oracle network) using the `requests` library.
    -   Simulates submitting the final transaction to the destination chain.

-   **`main()` function**: The entry point of the script. It handles configuration loading (from a `.env` file), instantiates the necessary classes, and starts the main simulation loop.

### Component Initialization

```python
# In main.py, components are initialized and wired together:
config = load_configuration() # Loads environment variables

# Set up connectors for both chains
source_chain = BlockchainConnector(config.SOURCE_RPC_URL)
dest_chain = BlockchainConnector(config.DEST_RPC_URL)

# Create the main relayer instance
relayer = BridgeRelayer(
    source_connector=source_chain,
    destination_connector=dest_chain,
    config=config
)

# Start the main processing loop
relayer.run_simulation_loop()
```

## How It Works

The simulation runs in a continuous loop, with each iteration representing a "cycle" of the relayer's operation.

1.  **Initialization**: The script starts by connecting to the specified RPC endpoints for both the source and destination chains.

2.  **Event Scanning**: In each cycle, the `BridgeRelayer` instructs the `EventScanner` to scan for new `TokensLocked` events on the source chain, starting from the last block it checked.

3.  **Transaction Creation**: For each new event found, a `CrossChainTransaction` object is created with the status `INITIATED` and added to the relayer's pool of active transactions.

4.  **State Processing**: The relayer then iterates through all active transactions and processes them based on their current status:
    -   **`INITIATED`**: It checks if the source transaction has received the required number of block confirmations. If so, its status is updated to `CONFIRMED_SOURCE`.
    -   **`CONFIRMED_SOURCE`**: It simulates a call to an external oracle or validator network to obtain a cryptographic signature needed to authorize minting on the destination chain. Upon success, the transaction's status is updated to `RELAY_PENDING`.
    -   **`RELAY_PENDING`**: It simulates building and sending the final transaction to the destination chain's bridge contract to mint the new tokens. Upon successful simulation, the status is updated to `COMPLETED`.
    -   **`FAILED`**: If any step fails repeatedly, the transaction is marked as `FAILED` with a reason.

5.  **Logging**: Throughout the process, detailed logs are printed to the console, showing the status of the relayer and each transaction it is processing.

6.  **Loop**: The script waits for a short interval (e.g., 15 seconds) before starting the next cycle.

## Usage

Follow these steps to set up and run the simulation.

### 1. Prerequisites

-   Python 3.8+
-   Access to two Ethereum-compatible JSON-RPC endpoints (e.g., from [Infura](https://infura.io/), [Alchemy](https://www.alchemy.com/), or a local node like [Ganache](https://trufflesuite.com/ganache/)).
-   Deployed bridge contract addresses on both chains.
-   The ABI (Application Binary Interface) for your bridge contract, typically as a JSON file. This file defines the contract's functions and events, allowing `web3.py` to interact with it.

### 2. Setup

First, clone the repository:
```bash
git clone https://github.com/your-username/Debuy.git
```

Navigate into the project directory:
```bash
cd Debuy
```

Create a Python virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

Install the required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration

Create a file named `.env` in the root of the project directory. Copy the example below into this file and replace the placeholder values with your actual data.

**Note**: The `.env` file contains sensitive information like API keys and private keys and should **not** be committed to version control. Ensure it is listed in your `.gitignore` file.

```env
# .env example

# RPC endpoint for the source chain (e.g., Ethereum Mainnet, Sepolia, etc.)
SOURCE_CHAIN_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID

# RPC endpoint for the destination chain (e.g., Polygon, Arbitrum, etc.)
DESTINATION_CHAIN_RPC_URL=https://polygon-mumbai.infura.io/v3/YOUR_INFURA_PROJECT_ID

# Deployed bridge contract address on the source chain
SOURCE_BRIDGE_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000001

# Deployed bridge contract address on the destination chain
DESTINATION_BRIDGE_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000002

# Private key of the relayer's wallet (prefixed with 0x)
# This account must have funds on the destination chain to pay for gas fees.
RELAYER_PRIVATE_KEY=0xyour_private_key_here_...

# Number of block confirmations to wait for on the source chain
CONFIRMATIONS_REQUIRED=12
```

### 4. Running the Script

Execute the main script from your terminal:

```bash
python main.py
```

You will see log output in your console as the relayer starts up, scans for blocks, and processes transactions.

**Example Output:**

```
2023-10-27 14:30:00 - INFO - [main] - Initializing Debuy Cross-Chain Bridge Relayer Simulation...
2023-10-27 14:30:01 - INFO - [Connector:SourceChain] - Successfully connected to SourceChain. Chain ID: 11155111
2023-10-27 14:30:02 - INFO - [Connector:DestinationChain] - Successfully connected to DestinationChain. Chain ID: 80001
2023-10-27 14:30:02 - INFO - [main] - Starting simulation loop. Press Ctrl+C to exit.
2023-10-27 14:30:02 - INFO - [main] - ==================== Cycle #1 ====================
2023-10-27 14:30:02 - INFO - [BridgeRelayer] - --- Starting new simulation cycle ---
2023-10-27 14:30:03 - INFO - [EventScanner:SourceChain] - Scanning for 'TokensLocked' events from block 4500101 to 4500125.
2023-10-27 14:30:04 - INFO - [EventScanner:SourceChain] - Found 1 new 'TokensLocked' event.
2023-10-27 14:30:04 - INFO - [BridgeRelayer] - New transaction initiated: 0xabc123...
2023-10-27 14:30:04 - INFO - [BridgeRelayer] - --- Cycle finished. Active transactions: 1 ---
...
```