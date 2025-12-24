# Pokémon Emerald

This is a decompilation of Pokémon Emerald.

It builds the following ROM:

* [**pokeemerald.gba**](https://datomatic.no-intro.org/index.php?page=show_record&s=23&n=1961) `sha1: f3ae088181bf583e55daf962a92bb46f4f1d07b7`

## Remote opponent builds (leader/follower)

These optional build variants are intended for emulator multiplayer-window setups.

Build the leader ROM:

* `make REMOTE_OPPONENT_LEADER=1 -j$(nproc)`
	* Outputs `pokeemerald.gba` by default

Build the follower ROM:

* `make REMOTE_OPPONENT_FOLLOWER=1 -j$(nproc)`
	* Outputs `follower.gba` by default

Optional output name overrides:

* `make ROM_NAME_OVERRIDE=myrom.gba`
* `make REMOTE_OPPONENT_LEADER=1 ROM_NAME_OVERRIDE=my_leader.gba`
* `make REMOTE_OPPONENT_FOLLOWER=1 ROM_NAME_OVERRIDE=my_follower.gba`

To set up the repository, see [INSTALL.md](INSTALL.md).

For contacts and other pret projects, see [pret.github.io](https://pret.github.io/).
