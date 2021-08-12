# maubot-poll
A simple matrix plugin for [maubot](https://github.com/maubot/maubot), which enables the creation of polls. 
The polls are *text-based*, so that they can also be used via bridges.

## Installation
Simply drag the plugin into the plugin folder, or upload it via maubot's user interface. You can download the plugin from the [releases](/releaes).

## Usage

- `!poll create <question> | <option 1> | <option 2> | <...>` -  Creates a new poll
- `!vote <code> <option>` - Vote for an option
- `!poll result <code>` - Shows the result of the poll
- `!poll ping <code> <option>` - Pings all participants who voted for `option`
