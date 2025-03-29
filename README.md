# debuy - Cross-Chain Bridge Event Listener & Relayer Simulation

This repository contains a Python-based simulation of a crucial backend component for a cross-chain bridge. It acts as an event listener and a transaction relayer, demonstrating the architectural patterns required to securely and reliably move information between two distinct blockchains.

The script is designed to be modular, robust, and showcases best practices such as state management, error handling, and interaction with external services.

## Concept

A cross-chain bridge allows users to transfer assets or data from a _source chain_ to a _destination chain_. The core mechanism of many bridges works as follows:

1.  A user locks their assets in a smart contract on the source chain. This action emits an event (e.g., `TokensLocked`).
2.  A network of off-chain listeners, known as relayers or validators, detects this event.
3.  After waiting for a certain number of block confirmations on the source chain (to prevent re-org attacks), the relayers reach a consensus.
4.  One of the relayers then submits a transaction to a smart contract on the destination chain to mint an equivalent amount of "wrapped" assets for the user.

This project simulates the off-chain **relayer** component (steps 2, 3, and 4). It connects to a source chain, scans for locking events, manages the transaction lifecycle, and simulates the final submission to the destination chain.

## Code Architecture

The script is architected with a separation of concerns, using several distinct classes to handle different responsibilities:

-   **`BlockchainConnector`**: A generic wrapper around the `web3.py` library. It manages the connection to a single blockchain's JSON-RPC endpoint and provides methods to get chain data and interact with contracts. An instance is created for both the source and destination chains.

-   **`EventScanner`**: Responsible for scanning a specific block range on a blockchain for a particular smart contract event. It uses the `BlockchainConnector` to perform its queries and efficiently filters for new events.

-   **`CrossChainTransaction`**: A data class that represents the state of a single bridging transaction. It tracks everything from the initial event data to its current status (e.g., `INITIATED`, `CONFIRMED_SOURCE`, `COMPLETED`, `FAILED`), transaction hashes, and other metadata.

-   **`BridgeRelayer`**: The central orchestrator. This class brings all other components together. It contains the main business logic for the bridging process:
    -   Initializes and manages the `EventScanner`.
    -   Maintains a dictionary of all `CrossChainTransaction` objects currently in flight.
    -   Implements the state machine for processing transactions from detection to completion.
    -   Handles logic for checking confirmations.
    -   Simulates interaction with external services (like an oracle network) using the `requests` library.
    -   Simulates submitting the final transaction to the destination chain.

-   **`main()` function**: The entry point of the script. It handles configuration loading (from a `.env` file), instantiates all the necessary classes, and runs the main simulation loop.

## How it Works

The simulation runs in a continuous loop, with each iteration representing a "cycle" of the relayer's operation.

1.  **Initialization**: The script starts by connecting to the specified RPC endpoints for both the source and destination chains.

2.  **Event Scanning**: In each cycle, the `BridgeRelayer` asks the `EventScanner` to scan for new `TokensLocked` events on the source chain, starting from the last block it checked.

3.  **Transaction Creation**: For each new event found, a `CrossChainTransaction` object is created with the status `INITIATED` and added to the relayer's list of active transactions.

4.  **State Processing**: The relayer then iterates through all active transactions and processes them based on their current status:
    -   **`INITIATED`**: It checks if the source transaction has received the required number of block confirmations. If so, its status is updated to `CONFIRMED_SOURCE`.
    -   **`CONFIRMED_SOURCE`**: It simulates a call to an external oracle or validator network via an HTTP request. This mimics the process of obtaining a cryptographic signature needed to authorize the minting on the destination chain. On success, the status changes to `RELAY_PENDING`.
    -   **`RELAY_PENDING`**: It simulates the final step of building and sending a transaction to the destination chain's bridge contract to mint the new tokens. Upon successful simulation, the status is updated to `COMPLETED`.
    -   **`FAILED`**: If any step fails repeatedly, the transaction is marked as `FAILED` with a reason.

5.  **Logging**: Throughout the process, detailed logs are printed to the console, showing the status of the relayer and each transaction it is processing.

6.  **Loop**: The script waits for a short interval (e.g., 15 seconds) before starting the next cycle.

## Usage Example

Follow these steps to set up and run the simulation.

### 1. Prerequisites

-   Python 3.8+
-   Access to two Ethereum-compatible JSON-RPC endpoints (e.g., from [Infura](https://infura.io/), [Alchemy](https://www.alchemy.com/), or a local node like [Ganache](https://trufflesuite.com/ganache/)). You'll need one for the source chain and one for the destination chain.
-   Deployed bridge contract addresses on both chains.

### 2. Setup

First, clone the repository:
```bash
git clone https://github.com/your-username/debuy.git
cd debuy
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

Create a file named `.env` in the root of the project directory. Add your configuration details to this file. **Replace the placeholder values with your actual data.**

```env
# .env file

# RPC endpoint for the source chain (e.g., Ethereum Mainnet, Sepolia, etc.)
SOURCE_CHAIN_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID

# RPC endpoint for the destination chain (e.g., Polygon, Arbitrum, etc.)
DESTINATION_CHAIN_RPC_URL=https://polygon-mumbai.infura.io/v3/YOUR_INFURA_PROJECT_ID

# Deployed bridge contract address on the source chain
SOURCE_BRIDGE_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000001

# Deployed bridge contract address on the destination chain
DESTINATION_BRIDGE_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000002
```

### 4. Running the Script

Execute the script from your terminal:

```bash
python script.py
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
2023-10-27 14:30:04 - INFO - [EventScanner:SourceChain] - Found 1 new 'TokensLocked' events.
2023-10-27 14:30:04 - INFO - [BridgeRelayer] - New transaction detected: 0xabc123...
2023-10-27 14:30:04 - INFO - [BridgeRelayer] - No active transactions to process.
2023-10-27 14:30:04 - INFO - [BridgeRelayer] - --- Cycle finished. Active transactions: 1 ---
  - Hash: 0xabc123... | Status: INITIATED | Amount: 1000000000000000000
...
```
