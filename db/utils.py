# db/utils.py

import sqlite3
import os

DB_FILE = "database.db"

def load_db_to_memory():
    """Load database from disk into an in-memory database"""
    if not os.path.exists(DB_FILE):
        print(f"Creating new database file: {DB_FILE}")
        open(DB_FILE, 'w').close()  # Create an empty file if it doesn't exist

    disk_conn = sqlite3.connect(DB_FILE)
    mem_conn = sqlite3.connect(":memory:")  # Create in-memory DB
    disk_conn.backup(mem_conn)  # Load data from disk
    disk_conn.close()
    return mem_conn

def save_memory_db_to_disk(mem_conn):
    """Save the in-memory database back to disk"""
    disk_conn = sqlite3.connect(DB_FILE)
    mem_conn.backup(disk_conn)  # Save memory data to disk
    disk_conn.close()
    print("Database saved to disk.")

def main():
    """Main function to handle database operations"""
    # Load the database from disk into memory
    conn = load_db_to_memory()
    cursor = conn.cursor()

    # Create a table first_sight_analysis if it doesn't exist
    cursor.execute("""
CREATE TABLE IF NOT EXISTS first_sight_analysis (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    trainId INTEGER NOT NULL DEFAULT -1,
    testId INTEGER NOT NULL DEFAULT -1,

    widthInput INTEGER,
    widthOutput INTEGER,
    ratioWidthInputOutput REAL,
    diffWidthInputOutput REAL,

    heightInput INTEGER,
    heightOutput INTEGER,
    ratioHeightInputOutput REAL,
    diffHeightInputOutput REAL,

    diffWidthHeightInput REAL,
    diffWidthHeightOutput REAL,
    ratioWidthHeightInput REAL,
    ratioWidthHeightOutput REAL,

    areaInput INTEGER,
    areaOutput INTEGER,
    ratioAreaInputOutput REAL,
    diffAreaInputOutput REAL,

    countBlocksInput INTEGER,
    countBlocksOutput INTEGER,
    ratioBlocksInputOutput REAL,
    diffBlocksInputOutput REAL,

    countZonesInput INTEGER,
    countZonesOutput INTEGER,
    ratioZonesInputOutput REAL,
    diffZonesInputOutput REAL,

    ratioBlocksAreaInput REAL,
    ratioBlocksAreaOutput REAL,
    diffRatioBlocksAreaInputOutput REAL,

    ratioZonesAreaInput REAL,
    ratioZonesAreaOutput REAL,
    diffRatioZonesAreaInputOutput REAL,

    countColorsInput INTEGER,
    countColorsOutput INTEGER,
    diffColorsInputOutput INTEGER,

    sumColorsInput INTEGER,
    sumColorsOutput INTEGER,
    diffSumColorsInputOutput INTEGER,

    ratioColorsBlocksInput REAL,
    ratioColorsBlocksOutput REAL,
    ratioColorsZonesInput REAL,
    ratioColorsZonesOutput REAL,
    diffRatioColorsBlocksInputOutput REAL,
    diffRatioColorsZonesInputOutput REAL,

    firstMostColorInput INTEGER,
    countFirstMostColorInput INTEGER,
    secondMostColorInput INTEGER,
    countSecondMostColorInput INTEGER,
    diffFirstSecondMostColorInput INTEGER,

    firstLeastColorInput INTEGER,
    countFirstLeastColorInput INTEGER,
    secondLeastColorInput INTEGER,
    countSecondLeastColorInput INTEGER,
    diffFirstSecondLeastColorInput INTEGER,

    firstMostColorOutput INTEGER,
    countFirstMostColorOutput INTEGER,
    secondMostColorOutput INTEGER,
    countSecondMostColorOutput INTEGER,
    diffFirstSecondMostColorOutput INTEGER,

    firstLeastColorOutput INTEGER,
    countFirstLeastColorOutput INTEGER,
    secondLeastColorOutput INTEGER,
    countSecondLeastColorOutput INTEGER,
    diffFirstSecondLeastColorOutput INTEGER,

    diffFirstMostColorInputOutput INTEGER,
    diffSecondMostColorInputOutput INTEGER,
    diffFirstLeastColorInputOutput INTEGER,
    diffSecondLeastColorInputOutput INTEGER,

    blockColorTouchingAllBordersInput INTEGER,
    blockColorTouchingAllBordersOutput INTEGER,

    middleSplitLineColorInput INTEGER,
    middleSplitLineColorOutput INTEGER,

    countOnePixelBlocksInput INTEGER,
    countOnePixelBlocksOutput INTEGER,
    diffOnePixelBlocksInputOutput INTEGER,
    
    countColorsWithoutBgInput  INTEGER,
    countColorsWithoutBgOutput INTEGER,
    countPixelsAloneInput      INTEGER,
    countPixelsAloneOutput     INTEGER,

    countUniqueBlockShapesInput INTEGER,
    countUniqueBlockShapesOutput INTEGER,
    diffUniqueBlockShapesInputOutput INTEGER,

    countUniqueZoneShapesInput INTEGER,
    countUniqueZoneShapesOutput INTEGER,
    diffUniqueZoneShapesInputOutput INTEGER,

    countRectanglesInput INTEGER,
    countRectanglesOutput INTEGER,
    diffRectanglesInputOutput INTEGER,

    countSquaresInput INTEGER,
    countSquaresOutput INTEGER,
    diffSquaresInputOutput INTEGER,

    countStraightLineInput INTEGER,
    countStraightLineOutput INTEGER,
    diffStraightLineInputOutput INTEGER,
    
    countSameBlocksInputOutput INTEGER,
    countRecoloredBlocksInputOutput INTEGER,
    countSameZonesInputOutput INTEGER,
    countRecoloredZonesInputOutput INTEGER,
    
    countBlockTouchingBorderInput INTEGER,
    countBlockTouchingBorderOutput INTEGER
);
    """)
    conn.commit()

    # Create a table first_sight_consistency if it doesn't exist
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS first_sight_consistency (
    filename TEXT NOT NULL,

    widthInput BOOLEAN,
    widthOutput BOOLEAN,
    ratioWidthInputOutput BOOLEAN,
    diffWidthInputOutput BOOLEAN,

    heightInput BOOLEAN,
    heightOutput BOOLEAN,
    ratioHeightInputOutput BOOLEAN,
    diffHeightInputOutput BOOLEAN,

    diffWidthHeightInput BOOLEAN,
    diffWidthHeightOutput BOOLEAN,
    ratioWidthHeightInput BOOLEAN,
    ratioWidthHeightOutput BOOLEAN,

    areaInput BOOLEAN,
    areaOutput BOOLEAN,
    ratioAreaInputOutput BOOLEAN,
    diffAreaInputOutput BOOLEAN,

    countBlocksInput BOOLEAN,
    countBlocksOutput BOOLEAN,
    ratioBlocksInputOutput BOOLEAN,
    diffBlocksInputOutput BOOLEAN,

    countZonesInput BOOLEAN,
    countZonesOutput BOOLEAN,
    ratioZonesInputOutput BOOLEAN,
    diffZonesInputOutput BOOLEAN,

    ratioBlocksAreaInput BOOLEAN,
    ratioBlocksAreaOutput BOOLEAN,
    diffRatioBlocksAreaInputOutput BOOLEAN,

    ratioZonesAreaInput BOOLEAN,
    ratioZonesAreaOutput BOOLEAN,
    diffRatioZonesAreaInputOutput BOOLEAN,

    countColorsInput BOOLEAN,
    countColorsOutput BOOLEAN,
    diffColorsInputOutput BOOLEAN,

    sumColorsInput BOOLEAN,
    sumColorsOutput BOOLEAN,
    diffSumColorsInputOutput BOOLEAN,

    ratioColorsBlocksInput BOOLEAN,
    ratioColorsBlocksOutput BOOLEAN,
    ratioColorsZonesInput BOOLEAN,
    ratioColorsZonesOutput BOOLEAN,
    diffRatioColorsBlocksInputOutput BOOLEAN,
    diffRatioColorsZonesInputOutput BOOLEAN,

    firstMostColorInput BOOLEAN,
    countFirstMostColorInput BOOLEAN,
    secondMostColorInput BOOLEAN,
    countSecondMostColorInput BOOLEAN,
    diffFirstSecondMostColorInput BOOLEAN,

    firstLeastColorInput BOOLEAN,
    countFirstLeastColorInput BOOLEAN,
    secondLeastColorInput BOOLEAN,
    countSecondLeastColorInput BOOLEAN,
    diffFirstSecondLeastColorInput BOOLEAN,

    firstMostColorOutput BOOLEAN,
    countFirstMostColorOutput BOOLEAN,
    secondMostColorOutput BOOLEAN,
    countSecondMostColorOutput BOOLEAN,
    diffFirstSecondMostColorOutput BOOLEAN,

    firstLeastColorOutput BOOLEAN,
    countFirstLeastColorOutput BOOLEAN,
    secondLeastColorOutput BOOLEAN,
    countSecondLeastColorOutput BOOLEAN,
    diffFirstSecondLeastColorOutput BOOLEAN,

    diffFirstMostColorInputOutput BOOLEAN,
    diffSecondMostColorInputOutput BOOLEAN,
    diffFirstLeastColorInputOutput BOOLEAN,
    diffSecondLeastColorInputOutput BOOLEAN,

    blockColorTouchingAllBordersInput BOOLEAN,
    blockColorTouchingAllBordersOutput BOOLEAN,

    middleSplitLineColorInput BOOLEAN,
    middleSplitLineColorOutput BOOLEAN,

    countOnePixelBlocksInput BOOLEAN,
    countOnePixelBlocksOutput BOOLEAN,
    diffOnePixelBlocksInputOutput BOOLEAN,

    countUniqueBlockShapesInput BOOLEAN,
    countUniqueBlockShapesOutput BOOLEAN,
    diffUniqueBlockShapesInputOutput BOOLEAN,

    countUniqueZoneShapesInput BOOLEAN,
    countUniqueZoneShapesOutput BOOLEAN,
    diffUniqueZoneShapesInputOutput BOOLEAN,

    countRectanglesInput BOOLEAN,
    countRectanglesOutput BOOLEAN,
    diffRectanglesInputOutput BOOLEAN,

    countSquaresInput BOOLEAN,
    countSquaresOutput BOOLEAN,
    diffSquaresInputOutput BOOLEAN,

    countStraightLineInput BOOLEAN,
    countStraightLineOutput BOOLEAN,
    diffStraightLineInputOutput BOOLEAN,
    
    countSameBlocksInputOutput BOOLEAN,
    countRecoloredBlocksInputOutput BOOLEAN,
    countSameZonesInputOutput BOOLEAN,
    countRecoloredZonesInputOutput BOOLEAN,
    
    countBlockTouchingBorderInput BOOLEAN,
    countBlockTouchingBorderOutput BOOLEAN
);
        """)
    conn.commit()

    # Create the object_analysis table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS object_analysis (
        id INTEGER PRIMARY KEY,
        filename TEXT NOT NULL,
        trainId INTEGER NOT NULL,
        testId INTEGER NOT NULL,

        isInsideInput BOOLEAN,
        isInsideOutput BOOLEAN,
        isInsideTrain BOOLEAN,
        isInsideTest BOOLEAN,
        isBlock BOOLEAN,
        isZone BOOLEAN,
        
        color INTEGER,
        minX INTEGER,
        minY INTEGER,
        maxX INTEGER,
        maxY INTEGER,

        height INTEGER,
        width INTEGER,
        ratioWidthHeight REAL,
        area INTEGER,
        pixelCount INTEGER,
        sizeOrder INTEGER,
        sizeOrderDesc INTEGER,
        hasOddPixelCount BOOLEAN,
        hasEvenPixelCount BOOLEAN,
        areaPerimeter INTEGER,
        pixelPerimeter INTEGER,
        ratioPixelsArea REAL,
        
        isBlack BOOLEAN,
        isBlue BOOLEAN,
        isRed BOOLEAN,
        isGreen BOOLEAN,
        isYellow BOOLEAN,
        isGrey BOOLEAN,
        isFuchsia BOOLEAN,
        isOrange BOOLEAN,
        isTeal BOOLEAN,
        isBrown BOOLEAN,
        
        isColorUnique BOOLEAN,
        
        isSquare BOOLEAN,
        isRectangle BOOLEAN,
        isLine BOOLEAN,
        isHorizontal BOOLEAN,
        isVertical BOOLEAN,
        diagonalLength REAL,
        
        orthoAdjacentZonesCount INTEGER,
        diagAdjacentZonesCount INTEGER,
        adjacentZonesCount INTEGER,
        
        orthoAdjacentBlocksCount INTEGER,
        diagAdjacentBlocksCount INTEGER,
        adjacentBlocksCount INTEGER,

        orthoNeighborColorCount INTEGER,
        orthoNeighborColorList TEXT,
        diagNeighborColorCount INTEGER,
        diagNeighborColorList TEXT,
        neighborColorCount INTEGER,
        neighborColorList TEXT,
        diffGridColorObjectColor INTEGER,
        sameColorBlocksCount INTEGER,
        sameColorZonesCount INTEGER,

        distanceFromTopBorder INTEGER,
        distanceFromBottomBorder INTEGER,
        distanceFromLeftBorder INTEGER,
        distanceFromRightBorder INTEGER,
        minRow INTEGER,
        minCol INTEGER,
        maxRow INTEGER,
        maxCol INTEGER,

        areaCenterX REAL,
        areaCenterY REAL,
        massCenterX REAL,
        massCenterY REAL,
        isHorizontallyCentered BOOLEAN,
        isVerticallyCentered BOOLEAN,
        isCentered BOOLEAN,

        isTouchingTop BOOLEAN,
        isTouchingBottom BOOLEAN,
        isTouchingLeft BOOLEAN,
        isTouchingRight BOOLEAN,
        isTouchingBorder BOOLEAN,
        
        isTouchingTopRight BOOLEAN,
        isTouchingBottomRight BOOLEAN,
        isTouchingTopLeft BOOLEAN,
        isTouchingBottomLeft BOOLEAN,
        isTouchingCorner BOOLEAN,

        blockHoleCountWithoutBorder INTEGER,
        blockHoleCountWithBorder INTEGER,
        zoneHoleCountWithoutBorder INTEGER,
        zoneHoleCountWithBorder INTEGER,
        blockCountInsideHolesWithoutBorder INTEGER,
        blockCountInsideHolesWithBorder INTEGER,
        zoneCountInsideHolesWithoutBorder INTEGER,
        zoneCountInsideHolesWithBorder INTEGER,
           
        countExactlyAlignZonesHorizontally  INTEGER,
        countExactlyAlignZonesVertically INTEGER,
        
        countExactlyAlignBlocksHorizontally  INTEGER,
        countExactlyAlignBlocksVertically INTEGER,
        
        countZonesAtTopLeft INTEGER,
        countZonesAtTop INTEGER,
        countZonesAtTopRight INTEGER,
        countZonesAtLeft INTEGER,
        countZonesAtRight INTEGER,
        countZonesAtBottomLeft INTEGER,
        countZonesAtBottom INTEGER,
        countZonesAtBottomRight INTEGER,
        
        countBlocksAtTopLeft INTEGER,
        countBlocksAtTop INTEGER,
        countBlocksAtTopRight INTEGER,
        countBlocksAtLeft INTEGER,
        countBlocksAtRight INTEGER,
        countBlocksAtBottomLeft INTEGER,
        countBlocksAtBottom INTEGER,
        countBlocksAtBottomRight INTEGER,
        
        isObjectRepeated BOOLEAN,

        hasHorizontalSymmetry BOOLEAN,
        hasVerticalSymmetry BOOLEAN,
        hasDiagonalSymmetry BOOLEAN,
        hasCounterDiagonalSymmetry BOOLEAN,
        hasRotationalSymmetry BOOLEAN,
        
        isEncapsulatedByBlockAndAloneWithBorder BOOLEAN,
        isEncapsulatedByBlockAndAloneWithoutBorder BOOLEAN,
        isEncapsulatedByZoneAndAloneWithBorder BOOLEAN,
        isEncapsulatedByZoneAndAloneWithoutBorder BOOLEAN,

        isPath BOOLEAN,
        isTree BOOLEAN,
        
        -- ► NEW per‐train mapping & relational fields
        isObjectUnique BOOLEAN,
        isTargetObjectPresent BOOLEAN,
        isTargetObjectUnique BOOLEAN,
        isShapeUnique BOOLEAN,
        isTargetShapePresent BOOLEAN,
        isTargetShapeUnique BOOLEAN,
    
        isObjectOneToOne BOOLEAN,
        isObjectOneToMany BOOLEAN,
        isObjectManyToOne BOOLEAN,
        isObjectManyToMany BOOLEAN,
        isShapeOneToOne BOOLEAN,
        isShapeOneToMany BOOLEAN,
        isShapeManyToOne BOOLEAN,
        isShapeManyToMany BOOLEAN,
    
        target_object_id INTEGER,
        isObjectDeleted BOOLEAN,
        isShapeDeleted BOOLEAN,
        isMoved BOOLEAN,
        isRotatedOrFlipped BOOLEAN,
        isRecolored BOOLEAN,
        isZoomed BOOLEAN,
        isGlued BOOLEAN,
    
        moveRelX INTEGER,
        moveRelY INTEGER,
        newPosX INTEGER,
        newPosY INTEGER,
        moveBehindColor INTEGER,
    
        rotateOrFlip TEXT,
        recolored TEXT,
        zoomX INTEGER,
        zoomY INTEGER,
        
        data TEXT NOT NULL
    );
    """)

    conn.commit()

    # Create table: shape
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shape (
        id INTEGER PRIMARY KEY,
        filename TEXT NOT NULL,
        height INTEGER NOT NULL,
        width INTEGER NOT NULL,
        pixel_count INTEGER NOT NULL,
        data TEXT NOT NULL
    );
    """)

    # Create table: shape_transformation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shape_transformation (
        id INTEGER PRIMARY KEY,
        shape_id INTEGER NOT NULL,
        color INTEGER NOT NULL,
        rotated_90 BOOLEAN NOT NULL DEFAULT 0,
        rotated_180 BOOLEAN NOT NULL DEFAULT 0,
        rotated_270 BOOLEAN NOT NULL DEFAULT 0,
        flipped_vert BOOLEAN NOT NULL DEFAULT 0,
        flipped_horiz BOOLEAN NOT NULL DEFAULT 0,
        flipped_vert_90 BOOLEAN NOT NULL DEFAULT 0,
        flipped_horiz_90 BOOLEAN NOT NULL DEFAULT 0,
        zoom_x INTEGER NOT NULL DEFAULT 1,
        zoom_y INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (shape_id) REFERENCES shape(id)
    );
    """)

    # Create table: shape_occurrence
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shape_occurrence (
        id INTEGER PRIMARY KEY,        
        shape_id INTEGER NOT NULL,
        shape_transformation_id INTEGER NOT NULL,
        isInsideInput BOOLEAN NOT NULL DEFAULT 0,
        isInsideOutput BOOLEAN NOT NULL DEFAULT 0,
        isInsideTrain BOOLEAN NOT NULL DEFAULT 0,
        isInsideTest BOOLEAN NOT NULL DEFAULT 0,
        trainId INTEGER NOT NULL DEFAULT -1,
        testId INTEGER NOT NULL DEFAULT -1,
        object_id INTEGER,
        minX INTEGER NOT NULL,
        minY INTEGER NOT NULL,
        FOREIGN KEY (shape_id) REFERENCES shape(id),
        FOREIGN KEY (shape_transformation_id) REFERENCES shape_transformation(id),
        FOREIGN KEY (object_id) REFERENCES object_analysis(id)
    );
    """)

    conn.commit()


    # Create table: sprite_analysis
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sprite_analysis (
    	id INTEGER PRIMARY KEY,
        filename TEXT NOT NULL,
        trainId INTEGER NOT NULL,
        testId INTEGER NOT NULL,

        isInsideInput BOOLEAN,
        isInsideOutput BOOLEAN,
        isInsideTrain BOOLEAN,
        isInsideTest BOOLEAN,
        isInsideBuffer BOOLEAN,

        isGrid BOOLEAN,
        isFromSplit BOOLEAN,
        isFromHole BOOLEAN,
        isFromCut BOOLEAN,
        isFromColorZone BOOLEAN,
        isFromPrevious BOOLEAN,

        minX INTEGER,
        minY INTEGER,
        maxX INTEGER,
        maxY INTEGER,

        nbColors,
        bgColor,

        height INTEGER,
        width INTEGER,
        ratioWidthHeight REAL,
        area INTEGER,
        pixelCount INTEGER,
        sizeOrder INTEGER,
        sizeOrderDesc INTEGER,
        hasOddPixelCount BOOLEAN,
        hasEvenPixelCount BOOLEAN,
        areaPerimeter INTEGER,
        pixelPerimeter INTEGER,
        ratioPixelsArea REAL,
        
        nbBlack INTEGER,
        nbBlue INTEGER,
        nbRed INTEGER,
        nbGreen INTEGER,
        nbYellow INTEGER,
        nbGrey INTEGER,
        nbFuchsia INTEGER,
        nbOrange INTEGER,
        nbTeal INTEGER,
        nbBrown INTEGER,
        colorPresent TEXT,
        colorAbsent TEXT,
        colorOrder TEXT,
        colorMost INTEGER,
        colorLeast INTEGER,

        isSquare BOOLEAN,
        isRectangle BOOLEAN,
        isLine BOOLEAN,
        isHorizontal BOOLEAN,
        isVertical BOOLEAN,
        diagonalLength REAL,
        
        distanceFromTopBorder INTEGER,
        distanceFromBottomBorder INTEGER,
        distanceFromLeftBorder INTEGER,
        distanceFromRightBorder INTEGER,
        minRow INTEGER,
        minCol INTEGER,
        maxRow INTEGER,
        maxCol INTEGER,

        areaCenterX REAL,
        areaCenterY REAL,
        massCenterX REAL,
        massCenterY REAL,
        isHorizontallyCentered BOOLEAN,
        isVerticallyCentered BOOLEAN,
        isCentered BOOLEAN,

        isTouchingTop BOOLEAN,
        isTouchingBottom BOOLEAN,
        isTouchingLeft BOOLEAN,
        isTouchingRight BOOLEAN,
        isTouchingBorder BOOLEAN,
        
        isTouchingTopRight BOOLEAN,
        isTouchingBottomRight BOOLEAN,
        isTouchingTopLeft BOOLEAN,
        isTouchingBottomLeft BOOLEAN,
        isTouchingCorner BOOLEAN,
                
        isSpriteRepeated BOOLEAN,

        hasHorizontalSymmetry BOOLEAN,
        hasVerticalSymmetry BOOLEAN,
        hasDiagonalSymmetry BOOLEAN,
        hasCounterDiagonalSymmetry BOOLEAN,
        hasRotationalSymmetry BOOLEAN,
                
        -- Presence & uniqueness flags
        isSpriteUnique       BOOLEAN,
        isTargetSpritePresent BOOLEAN,
        isTargetSpriteUnique  BOOLEAN,
    
        -- Cardinality relations
        isSpriteOneToOne     BOOLEAN,
        isSpriteOneToMany    BOOLEAN,
        isSpriteManyToOne    BOOLEAN,
        isSpriteManyToMany   BOOLEAN,
    
        -- Target and deletion flags
        target_sprite_id     INTEGER,
        isSpriteDeleted      BOOLEAN,
    
        -- Transformation flags
        isMoved              BOOLEAN,
        isRotatedOrFlipped   BOOLEAN,
        isRecolored          BOOLEAN,
        isZoomed             BOOLEAN,
        isGlued              BOOLEAN,
    
        -- Movement deltas & new position
        moveRelX             INTEGER,
        moveRelY             INTEGER,
        newPosX              INTEGER,
        newPosY              INTEGER,
        moveBehindColor      INTEGER,
    
        -- Transformation parameters
        rotateOrFlip         TEXT,
        recolored            TEXT,
        zoomX                INTEGER,
        zoomY                INTEGER,
        
        colorUniqueRatio REAL,
        colorUniqueOrder INTEGER,
        
        data TEXT NOT NULL
    );
    """)

    conn.commit()

    # 1) Create table: sprite_unique
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sprite_unique (
            id INTEGER PRIMARY KEY,
            sprite_id INTEGER NOT NULL,
            trainId INTEGER NOT NULL DEFAULT -1,
            testId INTEGER NOT NULL DEFAULT -1,
            filename TEXT NOT NULL,
            height INTEGER NOT NULL,
            width INTEGER NOT NULL,
            pixel_count INTEGER NOT NULL,
            nbBlack INTEGER,
            nbBlue INTEGER,
            nbRed INTEGER,
            nbGreen INTEGER,
            nbYellow INTEGER,
            nbGrey INTEGER,
            nbFuchsia INTEGER,
            nbOrange INTEGER,
            nbTeal INTEGER,
            nbBrown INTEGER,
            colorPresent TEXT,
            colorAbsent TEXT,
            colorOrder TEXT,
            colorMost INTEGER,
            colorLeast INTEGER,
            data TEXT NOT NULL
        );
        """)

    # 2) Create table: sprite_transformation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sprite_transformation (
            id INTEGER PRIMARY KEY,
            sprite_unique_id INTEGER NOT NULL,
            inverted BOOLEAN NOT NULL DEFAULT 0,
            rotated_90 BOOLEAN NOT NULL DEFAULT 0,
            rotated_180 BOOLEAN NOT NULL DEFAULT 0,
            rotated_270 BOOLEAN NOT NULL DEFAULT 0,
            flipped_vert BOOLEAN NOT NULL DEFAULT 0,
            flipped_horiz BOOLEAN NOT NULL DEFAULT 0,
            flipped_vert_90 BOOLEAN NOT NULL DEFAULT 0,
            flipped_horiz_90 BOOLEAN NOT NULL DEFAULT 0,
            zoom_x INTEGER NOT NULL DEFAULT 1,
            zoom_y INTEGER NOT NULL DEFAULT 1,
            recolored TEXT NOT NULL DEFAULT '[]',
            sprite_produce_id INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (sprite_unique_id) REFERENCES sprite_unique(id)
        );
        """)

    # 3) Create table: sprite_occurrence
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sprite_occurrence (
            id INTEGER PRIMARY KEY,
            sprite_unique_id INTEGER NOT NULL,
            sprite_transformation_id INTEGER NOT NULL,
            isInsideInput BOOLEAN NOT NULL DEFAULT 0,
            isInsideOutput BOOLEAN NOT NULL DEFAULT 0,
            isInsideTrain BOOLEAN NOT NULL DEFAULT 0,
            isInsideTest BOOLEAN NOT NULL DEFAULT 0,
            trainId INTEGER NOT NULL DEFAULT -1,
            testId INTEGER NOT NULL DEFAULT -1,
            sprite_id INTEGER,
            minX INTEGER NOT NULL,
            minY INTEGER NOT NULL,
            glued BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (sprite_unique_id) REFERENCES sprite_unique(id),
            FOREIGN KEY (sprite_transformation_id) REFERENCES sprite_transformation(id),
            FOREIGN KEY (sprite_id) REFERENCES sprite_analysis(id)
        );
        """)

    # 4) Create table: sprite_computation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sprite_computation (
            id INTEGER PRIMARY KEY,
            trainId INTEGER NOT NULL DEFAULT -1,
            sprite_id INTEGER NOT NULL,
            computation_id INTEGER NOT NULL,
            sub_sprite_id INTEGER NOT NULL,
            sub_rel_min_x INTEGER NOT NULL,
            sub_rel_min_y INTEGER NOT NULL,
            sub_min_x INTEGER NOT NULL,
            sub_min_y INTEGER NOT NULL,
            sub_width INTEGER NOT NULL,
            sub_height INTEGER NOT NULL,
            FOREIGN KEY (sprite_id) REFERENCES sprite_analysis(id),
            FOREIGN KEY (sub_sprite_id) REFERENCES sprite_analysis(id)
        );
        """)

    conn.commit()

    # Fetch and print data
    cursor.execute("SELECT * FROM first_sight_analysis LIMIT 1")
    print("first_sight_analysis in database:", cursor.fetchall())

    # Fetch and print data
    cursor.execute("SELECT * FROM first_sight_consistency LIMIT 1")
    print("first_sight_consistency in database:", cursor.fetchall())

    # Fetch and print data
    cursor.execute("SELECT * FROM object_analysis LIMIT 1")
    print("object_analysis in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM shape LIMIT 1")
    print("shape in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM shape_transformation  LIMIT 1")
    print("shape_transformation  in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM shape_occurrence LIMIT 1")
    print("shape_occurrence in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM sprite_analysis LIMIT 1")
    print("sprite_analysis in database:", cursor.fetchall())


    cursor.execute("SELECT * FROM sprite_unique  LIMIT 1")
    print("sprite_unique  in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM sprite_transformation LIMIT 1")
    print("sprite_transformation in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM sprite_occurrence LIMIT 1")
    print("sprite_occurrence in database:", cursor.fetchall())

    cursor.execute("SELECT * FROM sprite_computation LIMIT 1")
    print("sprite_computation in database:", cursor.fetchall())

    # Save the in-memory database to disk
    save_memory_db_to_disk(conn)

    # Close the connection
    conn.close()

if __name__ == "__main__":
    main()