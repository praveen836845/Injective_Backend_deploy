from flask import Flask, request, jsonify
from typing import Optional
import threading
import time
from datetime import datetime
import colorama
from colorama import Fore, Style
import requests
import json
from decimal import Decimal
from app.agent_manager import AgentManager
from flask_cors import CORS  #
# Initialize colorama for colored output
colorama.init()

app = Flask(__name__)
CORS(app)
class InjectiveAPI:
    """API interface for Injective Chain with agent management"""

    def __init__(self, api_url: str, debug: bool = False):
        self.api_url = api_url
        self.debug = debug
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.animation_stop = False
        self.agent_manager = AgentManager()

    def format_response(self, response_text, response_type=None):
        """Format and clean up the response text based on type."""
        if not response_text:
            return "No response"

        try:
            # Try to parse as JSON first
            response_data = (
                json.loads(response_text)
                if isinstance(response_text, str)
                else response_text
            )

            # Determine the type of response based on content
            if isinstance(response_data, dict):
                if "balances" in response_data:
                    return self.format_balance_response(response_data)
                elif any(
                    key in response_data for key in ["result", "gas_wanted", "gas_fee"]
                ):
                    return self.format_transaction_response(response_data)
        except:
            pass

        # Default formatting for regular messages
        return response_text

    def format_transaction_response(self, response):
        """Format blockchain transaction response."""
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except:
                return response

        if isinstance(response, dict):
            if "error" in response:
                return (
                    f"{Fore.RED}Transaction Error: {response['error']}{Style.RESET_ALL}"
                )

            result = []
            if "result" in response:
                tx_result = response["result"]
                result.append(f"{Fore.GREEN}Transaction Successful{Style.RESET_ALL}")
                if isinstance(tx_result, dict):
                    if "txhash" in tx_result:
                        result.append(f"Transaction Hash: {tx_result['txhash']}")
                    if "height" in tx_result:
                        result.append(f"Block Height: {tx_result['height']}")

            if "gas_wanted" in response:
                result.append(f"Gas Wanted: {response['gas_wanted']}")
            if "gas_fee" in response:
                result.append(f"Gas Fee: {response['gas_fee']}")

            return "\n".join(result)

        return str(response)

    def format_balance_response(self, response):
        """Format balance query response."""
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except:
                return response

        if isinstance(response, dict):
            if "error" in response:
                return f"{Fore.RED}Query Error: {response['error']}{Style.RESET_ALL}"

            if "balances" in response:
                result = [f"{Fore.CYAN}Account Balances:{Style.RESET_ALL}"]
                for token in response["balances"]:
                    amount = Decimal(token.get("amount", 0)) / Decimal(
                        10**18
                    )  # Convert from wei
                    denom = token.get("denom", "UNKNOWN")
                    result.append(f"- {amount:.8f} {denom}")
                return "\n".join(result)

        return str(response)

    def make_request(
        self, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None
    ) -> dict:
        """Make API request with current agent information"""
        try:
            url = f"{self.api_url.rstrip('/')}/{endpoint.lstrip('/')}"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Add any required authentication headers here
                # Example: "Authorization": f"Bearer {self.api_key}"
            }

            # Add current agent information to request if available
            current_agent = self.agent_manager.get_current_agent()
            if current_agent and data:
                data["agent_key"] = current_agent["private_key"]
                data["environment"] = self.agent_manager.get_current_network()
                data["agent_id"] = current_agent["address"]

            print("Making request to:", url)  # Debugging
            print("Request headers:", headers)  # Debugging
            print("Request payload:", data)  # Debugging

            response = requests.post(
                url, json=data, params=params, headers=headers, timeout=120
            )

            print("Response status code:", response.status_code)  # Debugging
            print("Response content:", response.text)  # Debugging

            # Raise an exception for HTTP errors (4xx, 5xx)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            if e.response.status_code == 403:
                error_message = e.response.json().get("error", "Forbidden")
                print("403 Error:", error_message)  # Debugging
                raise Exception(f"403 Forbidden: {error_message}")
            else:
                print("Request failed:", str(e))  # Debugging
                raise Exception(f"API request failed: {str(e)}")

# Initialize the InjectiveAPI instance
injective_api = InjectiveAPI(api_url="http://localhost:8000")

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat requests"""
    data = request.json
    user_input = data.get('message')

    if not user_input:
        return jsonify({"error": "Message is required"}), 400

    try:
        agent = injective_api.agent_manager.get_current_agent()
        print("checking that" , injective_api.agent_manager.get_current_network())
        if not agent:
            return jsonify({"error": "No agent selected"}), 400

        # Generate session_id on the backend
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")

        result = injective_api.make_request(
            "/chat",
            {
                "message": user_input,
                "session_id": session_id,  # Use the backend-generated session_id
                "agent_id": agent["address"],
                "agent_key": agent["private_key"],
                "environment": injective_api.agent_manager.get_current_network(),
            },
        )

        formatted_response = injective_api.format_response(result.get("response"))
        return jsonify({"response": formatted_response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/switch_network', methods=['POST'])
def switch_network():
    """Handle network switching"""
    data = request.json
    network = data.get('network')

    if not network or network.lower() not in ["mainnet", "testnet"]:
        return jsonify({"error": "Please specify 'mainnet' or 'testnet'"}), 400

    try:
        injective_api.agent_manager.current_agent = None
        injective_api.agent_manager.switch_network(network.lower())
        return jsonify({"message": f"Switched to {network.upper()}"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create_agent', methods=['POST'])
def create_agent():
    """Handle agent creation"""
    data = request.json
    agent_name = data.get('name')

    if not agent_name:
        return jsonify({"error": "Agent name is required"}), 400

    try:
        agent_info = injective_api.agent_manager.create_agent(agent_name)
        return jsonify({
            "message": f"Created agent '{agent_name}' on {injective_api.agent_manager.get_current_network().upper()}",
            "address": agent_info['address']
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete_agent', methods=['POST'])
def delete_agent():
    """Handle agent deletion"""
    data = request.json
    agent_name = data.get('name')

    if not agent_name:
        return jsonify({"error": "Agent name is required"}), 400

    try:
        injective_api.agent_manager.delete_agent(agent_name)
        return jsonify({"message": f"Deleted agent '{agent_name}'"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/switch_agent', methods=['POST'])
def switch_agent():
    """Handle agent switching"""
    data = request.json
    agent_name = data.get('name')

    if not agent_name:
        return jsonify({"error": "Agent name is required"}), 400

    try:
        injective_api.agent_manager.switch_agent(agent_name)
        return jsonify({
            "message": f"Switched to agent '{agent_name}' on {injective_api.agent_manager.get_current_network().upper()}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/list_agents', methods=['GET'])
def list_agents():
    """Handle listing agents"""
    try:
        mainnet_agents, testnet_agents = injective_api.agent_manager.get_agent_based_on_network()
        if injective_api.agent_manager.current_network == "mainnet":
            agents = mainnet_agents
        else:
            agents = testnet_agents

        return jsonify({
            "network": injective_api.agent_manager.current_network,
            "agents": agents
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)