"""Small stand-ins for SPNKr objects and the Halo client (no network)."""

import datetime as dt
import uuid
from types import SimpleNamespace as NS

from spnkr.models.refdata import GameVariantCategory, LifecycleMode, Outcome

T0 = dt.datetime(2026, 11, 26, 3, 0, tzinfo=dt.timezone.utc)
OUTCOMES = {"win": Outcome.WIN, "loss": Outcome.LOSS, "tie": Outcome.TIE}


def mid(n):
    return str(uuid.UUID(int=n))


def core(kills=10, deaths=5, assists=3, damage=3000, score=1000):
    return NS(score=score, personal_score=score, kills=kills, deaths=deaths, assists=assists,
              damage_dealt=damage, damage_taken=damage - 500, shots_fired=200, shots_hit=100,
              accuracy=50.0, headshot_kills=4, melee_kills=1, grenade_kills=1,
              power_weapon_kills=2, callout_assists=1, max_killing_spree=5, driver_assists=0,
              vehicle_destroys=0, hijacks=0, medals=(NS(name_id=1512363953, count=2),))


def match(n, start=T0, players=(), teams=((0, "win", 50), (1, "loss", 43)),
          category=GameVariantCategory.SLAYER, minutes=10):
    """players: [(xuid, team_id, outcome, kills)]"""
    asset = NS(asset_id=uuid.UUID(int=900 + n), version_id=uuid.UUID(int=901))
    info = NS(start_time=start, end_time=start + dt.timedelta(minutes=minutes),
              duration=dt.timedelta(minutes=minutes), lifecycle_mode=LifecycleMode.MATCHMADE,
              game_variant_category=category, map_variant=asset, ugc_game_variant=asset,
              playlist=NS(asset_id=uuid.UUID(int=77), version_id=uuid.UUID(int=78)),
              season_id="Season7")
    return NS(
        match_id=uuid.UUID(mid(n)), match_info=info,
        teams=tuple(NS(team_id=t, outcome=OUTCOMES[o], rank=1 if o == "win" else 2,
                       stats=NS(core_stats=NS(score=s))) for t, o, s in teams),
        players=tuple(NS(
            player_id=f"xuid({x})", last_team_id=team, outcome=OUTCOMES[o], rank=1,
            participation_info=NS(time_played=dt.timedelta(minutes=minutes),
                                  joined_in_progress=False, present_at_completion=True),
            player_team_stats=(NS(team_id=team, stats=NS(
                core_stats=core(kills=k), capture_the_flag_stats=None, oddball_stats=None,
                zones_stats=None, stockpile_stats=None, elimination_stats=None,
                extraction_stats=None, infection_stats=None, bomb_stats=None)),))
            for x, team, o, k in players),
    )


class _Resp:
    def __init__(self, value):
        self.value = value

    async def parse(self):
        return self.value


class FakeHalo:
    """histories: {xuid: [match objects, newest first]}"""

    def __init__(self, histories):
        self.histories = histories
        self.stats_calls = []
        self.history_calls = 0
        self.stats = NS(get_match_history=self._history, get_match_stats=self._stats)
        self.discovery_ugc = NS(get_map=self._name("Live Fire"),
                                get_playlist=self._name("Quick Play"))

    async def _history(self, xuid, start=0, count=25, match_type="all"):
        self.history_calls += 1
        items = self.histories.get(xuid, [])[start:start + count]
        return _Resp(NS(results=tuple(NS(match_id=m.match_id, match_info=m.match_info)
                                      for m in items)))

    async def _stats(self, match_id):
        self.stats_calls.append(str(match_id))
        for items in self.histories.values():
            for m in items:
                if str(m.match_id) == str(match_id):
                    return _Resp(m)
        raise KeyError(match_id)

    @staticmethod
    def _name(name):
        async def get(asset_id, version_id):
            return _Resp(NS(public_name=name))
        return get
