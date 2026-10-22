#ifndef GBC_ATLAS_ASSET_TYPES_H
#define GBC_ATLAS_ASSET_TYPES_H
#include <stdint.h>

/* Coordinates/dimensions in atlas cells; origins are pixel offsets within region.
 * Resolve each cell through the generated cell_tiles and cell_palettes arrays.
 * Palette IDs are local to this atlas, not an allocation of runtime palette slots.
 */
#define ASSET_KIND_TILE 0
#define ASSET_KIND_SPRITE 1

typedef struct AssetRegion {
    uint8_t x, y, width, height;
    uint8_t origin_x, origin_y;
    uint8_t kind;
    uint16_t duration_ms; /* Zero when not specified. */
} AssetRegion;
#endif
