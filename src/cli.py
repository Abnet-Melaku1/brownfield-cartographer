import argparse
import sys
import io

# Ensure UTF-8 output on Windows terminals that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.orchestrator import Orchestrator

def main():
    """Command Line Interface for The Brownfield Cartographer."""
    parser = argparse.ArgumentParser(
        description="The Brownfield Cartographer - FDE Codebase Intelligence System"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Analyze Command
    analyze_parser = subparsers.add_parser(
        "analyze", 
        help="Analyze a local repository and generate the knowledge graph"
    )
    analyze_parser.add_argument(
        "path", 
        help="Local path to the repository to analyze"
    )
    analyze_parser.add_argument(
        "--output", 
        default=".cartography", 
        help="Directory to place output JSON graphs (default: .cartography/)"
    )
    
    args = parser.parse_args()
    
    if args.command == "analyze":
        try:
            orchestrator = Orchestrator(output_dir=args.output)
            orchestrator.run_analysis(args.path)
        except Exception as e:
            print(f"[ERROR] Analysis failed: {e}")
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
