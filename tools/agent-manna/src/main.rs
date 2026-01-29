use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "manna-core")]
#[command(about = "Manna issue tracking system", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Create a new issue
    Create {
        /// Issue title
        title: String,
    },
    /// List all issues
    List,
    /// Show issue details
    Show {
        /// Issue ID
        id: String,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Some(Commands::Create { title }) => {
            println!("Creating issue: {}", title);
        }
        Some(Commands::List) => {
            println!("Listing issues");
        }
        Some(Commands::Show { id }) => {
            println!("Showing issue: {}", id);
        }
        None => {
            println!("manna-core - Issue tracking system");
            println!("Use --help for more information");
        }
    }
}
