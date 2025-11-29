# Pokémon Emerald Decompilation - AI Assistant Guide

This is a **decompilation project** that builds a byte-exact replica of Pokémon Emerald (GBA) from C and assembly sources.

## Build System Fundamentals

### Two Compilation Modes
- **Non-modern (default)**: Uses `agbcc`, a legacy GCC 2.95 compiler that matches the original build toolchain. Required for matching builds.
  - Build: `make` or `make compare`
  - Uses `tools/agbcc/bin/agbcc` compiler
  - Must install agbcc separately: `git clone https://github.com/pret/agbcc && cd agbcc && ./build.sh && ./install.sh ../pokeemerald`
- **Modern**: Uses `arm-none-eabi-gcc` from devkitARM for enhanced features and faster compilation
  - Build: `make modern`
  - Does not produce byte-exact match

### Build Commands
```bash
make                    # Build pokeemerald.gba (non-modern)
make compare            # Build and verify byte-exact match to original ROM
make modern             # Build with modern toolchain
make -j$(nproc)         # Parallel build (much faster)
make clean              # Remove build artifacts
make clean-tools        # Clean tool binaries (needed when switching terminals on Windows)
```

### Critical Build Dependencies
- **agbcc**: Custom compiler (non-modern builds only) - must be in sibling directory
- **libagbsyscall**: BIOS syscall library - built automatically
- **Custom build tools** in `tools/`: `gbagfx`, `mapjson`, `jsonproc`, `scaninc`, `preproc`, etc.
  - Auto-built on first `make` run
  - Graphics conversion, map JSON processing, dependency scanning

## Project Architecture

### Source Organization
```
src/           - C source files (game logic, battle system, UI, etc.)
asm/           - Assembly source files
data/          - Assembly data files and maps
  maps/        - Individual map definitions (JSON format)
  layouts/     - Map layout data
  scripts/     - Event scripts (.inc files)
include/       - Header files
  constants/   - Game constants (flags, vars, species, maps, etc.)
  global.h     - Core types and macros - included by virtually all C files
  config.h     - Build configuration (NDEBUG, BUGFIX, language settings)
graphics/      - PNG/PAL source files → converted to .4bpp/.8bpp/.gbapal
sound/         - Audio data (songs, sound effects)
```

### Code Conventions
- **Always include `global.h` first** in C files - it pulls in fundamental types and config
- **Struct offsets**: Many structs have offset comments like `/*0x000*/` for documentation
- **Fixed-point math**: Use macros like `Q_8_8(n)`, `Q_4_12(n)`, `Q_24_8(n)` for fixed-point numbers
- **Guard headers**: All headers use `#ifndef GUARD_<NAME>_H` pattern
- **Constants over magic numbers**: Use defines from `include/constants/` directories
- **Matching decompilation**: Per-file compiler flags in Makefile (lines 290-298) ensure certain files match exactly

### Special Makefile Patterns
- **File-specific compiler overrides**: Some files require specific compilers or flags:
  ```make
  $(C_BUILDDIR)/libc.o: CC1 := $(TOOLS_DIR)/agbcc/bin/old_agbcc$(EXE)
  $(C_BUILDDIR)/m4a.o: CC1 := tools/agbcc/bin/old_agbcc$(EXE)
  ```
- **Auto-generated targets**: Graphics and map data are generated from source files (see `graphics_file_rules.mk`, `map_data_rules.mk`)

## Map System

Maps are defined in **JSON format** (`data/maps/<MapName>/map.json`) containing:
- Map metadata (music, weather, flags)
- Object events (NPCs, items, warp points)
- Connections to other maps
- Scripts (referenced from `data/scripts/`)

Maps are compiled into binary data via `mapjson` tool. The build system auto-generates:
- `data/maps/headers.inc`
- `data/maps/connections.inc`
- `data/maps/events.inc`

## Graphics Pipeline

PNG/PAL files → `gbagfx` tool → GBA format (.4bpp/.8bpp/.gbapal/.lz/.rl)
- Conversion rules: `graphics_file_rules.mk`
- Sprites, tilesets, UI elements all follow this pattern
- Compressed graphics use `.lz` (LZ77) or `.rl` (run-length encoding)

## Common Pitfalls

1. **Missing agbcc**: Non-modern builds fail without agbcc in `../agbcc/`
2. **Switching build environments**: Run `make clean-tools` when switching terminals on Windows
3. **Parallel dependency issues**: Tools must be built before main compilation - Makefile handles this via `SETUP_PREREQS`
4. **Modern vs non-modern mixing**: Cannot compare modern builds to original ROM
5. **Include order**: `global.h` must come first, then constants, then local headers

## Debugging & Development

- **Debug builds**: `make modern DINFO=1` enables debug symbols
- **Symbol files**: `make syms` generates symbol map from ELF
- **Config flags**: Edit `include/config.h` to enable `BUGFIX` or debug printing
- **Dependency scanning**: `scaninc` tool auto-detects header dependencies

## Key Macros & Types

```c
ARRAY_COUNT(arr)       // Array length
SWAP(a, b, temp)       // Swap values
min(a, b), max(a, b)   // Math utilities
Q_8_8(n), Q_4_12(n)    // Fixed-point conversions
BLOCK_CROSS_JUMP       // Prevents optimization
```

## Related Tools

- **porymap**: Visual map editor (external)
- **poryscript**: Scripting language alternative (external)
- **Tilemap Studio**: Tilemap viewing/editing (external)

## Language & Platform

- **Language**: Mixed C (GNU89 for non-modern) and ARM assembly
- **Target**: Game Boy Advance (ARMv4T, ARM7TDMI CPU)
- **Endianness**: Little-endian
- **ROM format**: GBA ROM with specific header (TITLE, GAME_CODE, MAKER_CODE)
