from .event_parser import *
from collections import defaultdict
from traceback import print_exc
from datetime import datetime

import sc2reader
from sc2reader.engine.plugins import APMTracker, ContextLoader, SelectionTracker


class ReplayData:
    __parsers__ = [
        handle_expansion_events, handle_worker_events, handle_supply_events,
        handle_mineral_events, handle_vespene_events, handle_ground_events,
        handle_air_events, handle_tech_events, handle_upgrade_events,
        handle_unit_events
    ]

    @classmethod
    def parse_replay(cls,
                     replay=None,
                     replay_file=None,
                     file_object=None):

        replay_data = ReplayData(replay_file)
        try:
            # This is the engine that holds some required plugins for parsing
            engine = sc2reader.engine.GameEngine(
                plugins=[ContextLoader(),
                         APMTracker(),
                         SelectionTracker()])

            if replay:
                pass
            elif replay_file and not file_object:
                # Then we are not using ObjectStorage for accessing replay files
                replay = sc2reader.load_replay(replay_file, engine=engine)
            elif file_object:
                # We are using ObjectStorage to access replay files
                replay = sc2reader.load_replay(file_object, engine=engine)
            else:
                pass

            # Get the number of frames (one frame is 1/16 of a second)
            replay_data.frames = replay.frames
            # Gets the game mode (if available)
            replay_data.game_mode = replay.real_type
            # Gets the map hash (if we want to download the map, or do map-based analysis)
            replay_data.map_hash = replay.map_hash

            # Use the parsers to get data
            for event in replay.events:
                for parser in cls.__parsers__:
                    parser(replay_data, event)

            # Check if there was a winner
            if replay.winner is not None:
                replay_data.winners = replay.winner.players
                replay_data.losers = [
                    p for p in replay.players if p not in replay.winner.players
                ]
            else:
                replay_data.winners = []
                replay_data.losers = []
            # Check to see if expansion data is available
            replay_data.expansion = replay.expansion
            return replay_data
        except:
            # print our error and return NoneType object
            print_exc()
            return None

    def as_dict(self):
        return {
            "processed_on":
            datetime.utcnow().isoformat(),
            "replay_name":
            self.replay,
            "expansion":
            self.expansion,
            "frames":
            self.frames,
            "mode":
            self.game_mode,
            "map":
            self.map_hash,
            "matchup":
            "v".join(
                sorted([
                    s.detail_data["race"][0].upper()
                    for s in self.winners + self.losers
                ])),
            "winners":
            [(s.pid, s.name, s.detail_data['race']) for s in self.winners],
            "losers":
            [(s.pid, s.name, s.detail_data['race']) for s in self.losers],
            "stats_names": [k for k in self.players[1].keys()],
            "stats": {player: data
                      for player, data in self.players.items()}
        }

    def __init__(self, replay):
        self.players = defaultdict(lambda: defaultdict(list))
        self.replay = replay
        self.winners = []
        self.losers = []
        self.expansion = None
