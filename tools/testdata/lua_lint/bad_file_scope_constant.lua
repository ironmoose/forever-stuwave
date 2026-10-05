-- File-scope use of a constant that is declared `local` further down.
-- INSET compiles to a global read (nil at runtime), so this line throws.
local width = 100 - INSET

local INSET = 4

return width + INSET
