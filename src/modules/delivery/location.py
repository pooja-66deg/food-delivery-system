"""Driver availability + live location backed by Redis (GEO + a set).

- ``drivers:online`` — a set of driver ids currently accepting work.
- ``drivers:geo``    — a GEO index of each online driver's last known position.
"""
from redis.asyncio import Redis

_GEO_KEY = "drivers:geo"
_ONLINE_KEY = "drivers:online"


async def set_online(redis: Redis, driver_id: int, online: bool) -> None:
    if online:
        await redis.sadd(_ONLINE_KEY, str(driver_id))
    else:
        await redis.srem(_ONLINE_KEY, str(driver_id))
        await redis.zrem(_GEO_KEY, str(driver_id))


async def is_online(redis: Redis, driver_id: int) -> bool:
    return bool(await redis.sismember(_ONLINE_KEY, str(driver_id)))


async def update_location(redis: Redis, driver_id: int, latitude: float, longitude: float) -> None:
    """Record the driver's position (GEOADD) and mark them online."""
    await redis.geoadd(_GEO_KEY, (longitude, latitude, str(driver_id)))
    await redis.sadd(_ONLINE_KEY, str(driver_id))


async def get_location(redis: Redis, driver_id: int) -> dict | None:
    pos = await redis.geopos(_GEO_KEY, str(driver_id))
    if not pos or pos[0] is None:
        return None
    longitude, latitude = pos[0]
    return {"latitude": latitude, "longitude": longitude}


async def nearby_driver_ids(
    redis: Redis, latitude: float, longitude: float, radius_km: float = 10, count: int = 10
) -> list[int]:
    """Online driver ids near a point, closest first (GEOSEARCH)."""
    ids = await redis.geosearch(
        _GEO_KEY, longitude=longitude, latitude=latitude,
        radius=radius_km, unit="km", sort="ASC", count=count,
    )
    return [int(i) for i in ids]
