#!/usr/bin/env python3
"""CLI chat interface using Claude with MCP agents."""

import json
from dotenv import load_dotenv
from chat.claude_main import ClaudeAgentSystem

load_dotenv()


def format_results(data) -> str:
    """Format query results for display."""
    if not data:
        return "No data returned."

    if isinstance(data, str):
        return data

    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"

    if not isinstance(data, list) or not data:
        return json.dumps(data, indent=2)

    # Ensure all items are dictionaries
    if not all(isinstance(item, dict) for item in data):
        return json.dumps(data, indent=2)

    # TABLE PRINTOUT
    output = []
    headers = list(data[0].keys())

    # Calculate column widths
    col_widths = {h: len(h) for h in headers}
    for row in data:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ''))))

    # Header row
    header_row = " | ".join(h.ljust(col_widths[h]) for h in headers)
    output.append(header_row)
    output.append("-" * len(header_row))

    # Data rows
    for row in data[:50]:  # Limit to 50 rows
        data_row = " | ".join(str(row.get(h, '')).ljust(col_widths[h]) for h in headers)
        output.append(data_row)

    if len(data) > 50:
        output.append(f"\n... and {len(data) - 50} more rows")

    output.append(f"\nTotal rows: {len(data)}")

    return "\n".join(output)


def chat():
    """Main chat loop using Claude with MCP agents."""

    print("\n" + "="*80)
    print("NC Budget & Vendor Database Chat - Powered by Claude")
    print("="*80)
    print("Ask questions about NC budget and vendor data.")
    print("Type 'exit' or 'quit' to exit.\n")

    try:
        # Initialize Claude system
        claude_system = ClaudeAgentSystem()

        while True:
            try:
                user_input = input("[You] ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n[SYSTEM] Goodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n[SYSTEM] Goodbye!")
                break

            try:
                # Process message through Claude with MCP agents
                claude_system.process_message(user_input)

            except Exception as e:
                print(f"\n[ERROR] {str(e)}")
                import traceback
                traceback.print_exc()

    except KeyboardInterrupt:
        print("\n\n[SYSTEM] Interrupted.")
    except Exception as e:
        print(f"\n[FATAL] {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure cleanup
        if 'claude_system' in locals():
            claude_system.shutdown()
        print("\n[SYSTEM] Chat ended.")


if __name__ == "__main__":
    chat()
