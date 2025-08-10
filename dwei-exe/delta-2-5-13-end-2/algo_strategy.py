import gamelib
import random
import math
import warnings
from sys import maxsize
import json


"""
Turret Defense + Scout Rush Strategy:
1. Build comprehensive turret defense network
2. 3-Phase Attack System (ALWAYS rebuilds defenses after each attack):
   - Phase 1: ADD funnel turret at [22,11], REMOVE turrets at blocking_turret_position2 (MP >= 15)
   - Phase 2: Deploy 3 scouts at [13,0] + 12 scouts at [11,2] AND remove funnel turret [22,11] (same turn)
   - Phase 3: ALWAYS rebuild all blocking_turret_position2 turrets and reset all flags (next turn)
3. Hard reset to normal defensive state before each new attack cycle
"""

class AlgoStrategy(gamelib.AlgoCore):
    def __init__(self):
        super().__init__()
        seed = random.randrange(maxsize)
        random.seed(seed)
        gamelib.debug_write('Random seed: {}'.format(seed))

    def on_game_start(self, config):
        """ 
        Read in config and perform any initial setup here 
        """
        gamelib.debug_write('Configuring Turret Defense Strategy...')
        self.config = config
        global WALL, SUPPORT, TURRET, SCOUT, DEMOLISHER, INTERCEPTOR, MP, SP
        WALL = config["unitInformation"][0]["shorthand"]
        SUPPORT = config["unitInformation"][1]["shorthand"]
        TURRET = config["unitInformation"][2]["shorthand"]
        SCOUT = config["unitInformation"][3]["shorthand"]
        DEMOLISHER = config["unitInformation"][4]["shorthand"]
        INTERCEPTOR = config["unitInformation"][5]["shorthand"]
        MP = 1
        SP = 0
        
        # Defense setup tracking
        self.scored_on_locations = []
        self.ready_for_scout_rush = False
        self.turret_removed_for_attack = False
        self.attack_path_cleared = False  # Hardcoded indicator for attack readiness
        
        # Corner wall positions (replace turrets at [0,13] and [27,13])
        self.corner_walls = [[0,13], [27,13]]
        
        # Primary turret defense positions
        self.primary_turrets = [[1,12],[1,13],[2,12],[2,13],[3,13],[4,13],[5,13],[6,13],[7,12],[8,12],[9,12],[10,12],[11,12],[15,10],[16,11],[17,12],[18,12],[19,12],[20,12],[21,12],[22,12],[23,12],[24,12],[24,13],[25,12],[25,13],[26,12],[26,13], [12,12],[13,12],[14,11]]
        
        # Secondary turret positions (build after primary complete)
        self.secondary_turrets = [[3,12],[24,11],[25,11]]
        
        # Support positions (build after all turrets complete)
        self.support_positions = [[3,12],[4,12],[5,12],[6,12],[4,11]]
        
        # Attack positions and blocking turret logic
        self.scout_attack_position1 = [12,1]  # 3 scouts
        self.scout_attack_position2 = [14,0]  # 12 scouts
        self.blocking_turret_position2 = [[1,13],[1,12],[2,12]]  # REMOVE during attack prep
        
        # Escalating attack wave system - increases by 2 MP after each attack
        self.min_attack_mp = 13  # Starting threshold for first attack
        self.attack_cycles_completed = 0  # Track number of completed attack cycles

    def on_turn(self, turn_state):
        """
        Main strategy execution
        """
        game_state = gamelib.GameState(self.config, turn_state)
        gamelib.debug_write('Turn {} - Turret Defense Strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)

        # Execute defensive strategy
        self.execute_defensive_strategy(game_state)
        
        # Execute attack strategy 
        self.execute_attack_strategy(game_state)

        game_state.submit_turn()

    def execute_defensive_strategy(self, game_state):
        """
        NEW PRIORITY SYSTEM - Fixed defensive strategy execution
        """
        # Always maintain corner walls first
        self.build_and_maintain_corner_walls(game_state)
        
        # STEP 1: Ensure all primary and secondary turrets are built
        self.build_primary_and_secondary_turrets(game_state)
        
        # STEP 2: Mark damaged turrets for removal (below 30% health)
        self.mark_damaged_turrets_for_removal(game_state)
        
        # STEP 3: Build all support structures (build one, upgrade immediately, then next)
        self.build_support_structures_sequential(game_state)
        
        # STEP 4: Only after all supports are built, upgrade remaining turrets
        if self.all_supports_built_and_upgraded(game_state):
            self.upgrade_turrets_by_priority(game_state)

    def build_and_maintain_corner_walls(self, game_state):
        """
        Build and maintain corner walls at [0,13] and [27,13] with instant upgrades
        """
        for location in self.corner_walls:
            wall_needs_attention = False
            # Check if wall exists and its health
            if game_state.contains_stationary_unit(location):
                units_at_location = game_state.game_map[location]
                for unit in units_at_location:
                    if unit.player_index == 0:  # Our unit
                        # Check if health is below 40%
                        if unit.health < (unit.max_health * 0.4):
                            wall_needs_attention = True
                            gamelib.debug_write('Corner wall at {} below 40% health ({}/{}), replacing...'.format(
                                location, unit.health, unit.max_health))
                            break
            else:
                # No wall exists, need to build one
                wall_needs_attention = True
                gamelib.debug_write('No corner wall at {}, building...'.format(location))
            
            # Replace/build and upgrade wall if needed
            if wall_needs_attention:
                # Remove existing unit if present
                if game_state.contains_stationary_unit(location):
                    game_state.attempt_remove([location])
                
                # Build new wall
                if game_state.can_spawn(WALL, location):
                    if game_state.attempt_spawn(WALL, location):
                        gamelib.debug_write('Built corner wall at {}'.format(location))
                        # Instantly upgrade the wall
                        game_state.attempt_spawn(WALL, location)
                        game_state.attempt_upgrade([location])

    def build_primary_and_secondary_turrets(self, game_state):
        """
        STEP 1: Build all primary and secondary turrets
        """
        turrets_built = 0
        
        # Build primary turrets first
        for location in self.primary_turrets:
            # Skip blocking turrets during attack preparation/execution
            if self.attack_path_cleared and location in self.blocking_turret_position2:
                continue
                
            if not game_state.contains_stationary_unit(location):
                if game_state.can_spawn(TURRET, location):
                    game_state.attempt_spawn(TURRET, location)
                    turrets_built += 1
                    gamelib.debug_write('STEP 1: Built primary turret at {}'.format(location))
        
        # Build secondary turrets after primary
        for location in self.secondary_turrets:
            if not game_state.contains_stationary_unit(location):
                if game_state.can_spawn(TURRET, location):
                    game_state.attempt_spawn(TURRET, location)
                    turrets_built += 1
                    gamelib.debug_write('STEP 1: Built secondary turret at {}'.format(location))
        
        if turrets_built > 0:
            gamelib.debug_write('STEP 1 COMPLETE: Built {} turrets'.format(turrets_built))

    def mark_damaged_turrets_for_removal(self, game_state):
        """
        STEP 2: Mark turrets below 30% health for removal (they will be rebuilt in STEP 1 next turn)
        """
        turrets_marked = 0
        all_turret_positions = self.primary_turrets + self.secondary_turrets
        
        for location in all_turret_positions:
            # Skip blocking turrets during attack preparation/execution
            if self.attack_path_cleared and location in self.blocking_turret_position2:
                continue
                
            if game_state.contains_stationary_unit(location):
                units_at_location = game_state.game_map[location]
                for unit in units_at_location:
                    if unit.player_index == 0 and unit.health < (unit.max_health * 0.5):
                        # Mark for removal - it will be rebuilt next turn in STEP 1
                        game_state.attempt_remove([location])
                        turrets_marked += 1
                        gamelib.debug_write('STEP 2: Marked damaged turret at {} for removal (Health: {}/{})'.format(
                            location, unit.health, unit.max_health))
                        break
        
        if turrets_marked > 0:
            gamelib.debug_write('STEP 2 COMPLETE: Marked {} damaged turrets for removal'.format(turrets_marked))

    def build_support_structures_sequential(self, game_state):
        """
        STEP 3: Build support structures one by one, upgrading each immediately after building
        """
        # Only proceed if all turrets are built
        if not self.all_turrets_built(game_state):
            gamelib.debug_write('STEP 3 SKIPPED: Not all turrets built yet')
            return
        
        supports_built = 0
        supports_upgraded = 0
        
        # Find the first support position that needs building or upgrading
        for i, location in enumerate(self.support_positions):
            if not game_state.contains_stationary_unit(location):
                # No support exists, build it
                if game_state.can_spawn(SUPPORT, location):
                    if game_state.attempt_spawn(SUPPORT, location):
                        supports_built += 1
                        gamelib.debug_write('STEP 3: Built support at {} (position {})'.format(location, i))
                        
                        # Immediately try to upgrade it
                        if game_state.get_resource(SP) >= 5:  # Cost to upgrade support
                            if game_state.attempt_upgrade([location]):
                                supports_upgraded += 1
                                gamelib.debug_write('STEP 3: Immediately upgraded support at {}'.format(location))
                            else:
                                gamelib.debug_write('STEP 3: Built support at {} but could not upgrade (insufficient SP)'.format(location))
                        else:
                            gamelib.debug_write('STEP 3: Built support at {} but need more SP to upgrade next turn'.format(location))
                        
                        # Only build one support per turn, exit
                        break
                else:
                    gamelib.debug_write('STEP 3: Cannot afford to build support at {}'.format(location))
                    break
            else:
                # Support exists, check if it needs upgrading
                units_at_location = game_state.game_map[location]
                for unit in units_at_location:
                    if unit.player_index == 0:  # Our unit
                        if not unit.upgraded:
                            # Support exists but not upgraded, try to upgrade it
                            if game_state.get_resource(SP) >= 5:
                                if game_state.attempt_upgrade([location]):
                                    supports_upgraded += 1
                                    gamelib.debug_write('STEP 3: Upgraded existing support at {} (position {})'.format(location, i))
                                else:
                                    gamelib.debug_write('STEP 3: Failed to upgrade support at {} (insufficient SP)'.format(location))
                            else:
                                gamelib.debug_write('STEP 3: Support at {} needs upgrading but insufficient SP'.format(location))
                            # Exit after handling this unupgraded support
                            break
                        else:
                            # This support is already upgraded, continue to next position
                            continue
                # Check if we handled an unupgraded support and should exit
                if game_state.contains_stationary_unit(location):
                    units_at_location = game_state.game_map[location]
                    for unit in units_at_location:
                        if unit.player_index == 0 and not unit.upgraded:
                            # We handled this case above, exit
                            break
                    else:
                        # Support is upgraded, continue to next position
                        continue
                    break
        
        if supports_built > 0 or supports_upgraded > 0:
            gamelib.debug_write('STEP 3 COMPLETE: Built {} supports, upgraded {} supports'.format(supports_built, supports_upgraded))

    def upgrade_turrets_by_priority(self, game_state):
        """
        STEP 4: Upgrade turrets by priority (only after all supports are built and upgraded)
        """
        sp = int(game_state.get_resource(SP))
        initial_sp = sp
        upgrades_made = 0
        
        # Priority order: closest to enemy front line first
        priority_turret_positions = [[24,13], [25,13], [3,13], [2,13], [24,12], [25,12]]
        
        # Upgrade priority turrets first
        for location in priority_turret_positions:
            if sp < 5:  # Not enough SP for upgrades
                break
                
            # Skip blocking turrets during attack preparation/execution
            if self.attack_path_cleared and location in self.blocking_turret_position2:
                continue
            
            if game_state.contains_stationary_unit(location):
                units_at_location = game_state.game_map[location]
                for unit in units_at_location:
                    if unit.player_index == 0 and not unit.upgraded:
                        if game_state.attempt_upgrade([location]):
                            upgrades_made += 1
                            sp -= 5  # Assume upgrade cost is 5
                            gamelib.debug_write('STEP 4: Upgraded priority turret at {} (SP remaining: {})'.format(
                                location, sp))
                            break
        
        # Upgrade remaining primary turrets
        for location in self.primary_turrets:
            if sp < 5:
                break
                
            if location in priority_turret_positions:  # Skip already processed
                continue
                
            # Skip blocking turrets during attack preparation/execution
            if self.attack_path_cleared and location in self.blocking_turret_position2:
                continue
            
            if game_state.contains_stationary_unit(location):
                units_at_location = game_state.game_map[location]
                for unit in units_at_location:
                    if unit.player_index == 0 and not unit.upgraded:
                        if game_state.attempt_upgrade([location]):
                            upgrades_made += 1
                            sp -= 5
                            gamelib.debug_write('STEP 4: Upgraded primary turret at {} (SP remaining: {})'.format(
                                location, sp))
                            break
        
        # Upgrade secondary turrets last
        for location in self.secondary_turrets:
            if sp < 5:
                break
            
            if game_state.contains_stationary_unit(location):
                units_at_location = game_state.game_map[location]
                for unit in units_at_location:
                    if unit.player_index == 0 and not unit.upgraded:
                        if game_state.attempt_upgrade([location]):
                            upgrades_made += 1
                            sp -= 5
                            gamelib.debug_write('STEP 4: Upgraded secondary turret at {} (SP remaining: {})'.format(
                                location, sp))
                            break
        
        if upgrades_made > 0:
            gamelib.debug_write('STEP 4 COMPLETE: Upgraded {} turrets (SP spent: {})'.format(
                upgrades_made, initial_sp - sp))

    def all_turrets_built(self, game_state):
        """
        Check if all primary and secondary turrets are built
        """
        # Check primary turrets
        for location in self.primary_turrets:
            # Skip blocking turrets during attack preparation/execution
            if self.attack_path_cleared and location in self.blocking_turret_position2:
                continue
            if not game_state.contains_stationary_unit(location):
                return False
        
        # Check secondary turrets
        for location in self.secondary_turrets:
            if not game_state.contains_stationary_unit(location):
                return False
        
        return True

    def all_supports_built_and_upgraded(self, game_state):
        """
        Check if all support structures are built and upgraded
        """
        for location in self.support_positions:
            if not game_state.contains_stationary_unit(location):
                return False  # Support not built yet
            
            units_at_location = game_state.game_map[location]
            for unit in units_at_location:
                if unit.player_index == 0 and not unit.upgraded:
                    return False  # Support exists but not upgraded
        
        return True  # All supports are built and upgraded

    def execute_attack_strategy(self, game_state):
        """
        Execute attack strategy: ESCALATING scout rush with increasing MP thresholds
        """
        mp = int(game_state.get_resource(MP))  # Convert to integer to avoid float errors
        
        # ESCALATING ATTACK SYSTEM: Check if we're ready for scout rush using dynamic threshold
        # Threshold increases by +2 after each completed attack cycle
        if mp >= self.min_attack_mp and not self.ready_for_scout_rush and not self.turret_removed_for_attack:
            self.ready_for_scout_rush = True
            expected_wave1 = 5 + (self.attack_cycles_completed * 2)
            expected_total_min = expected_wave1 + (mp - expected_wave1)
            gamelib.debug_write('🚀 DUAL ESCALATING SCOUT RUSH ACTIVATED! 🚀')
            gamelib.debug_write('MP: {} >= Threshold: {} | Attack Cycle: {} | Wave 1: {} scouts | Total Wave: ~{} scouts'.format(
                mp, self.min_attack_mp, self.attack_cycles_completed + 1, expected_wave1, expected_total_min))
            gamelib.debug_write('DUAL ESCALATION: Wave 1 AND MP threshold both increase by +2 each cycle!')
            gamelib.debug_write('PROGRESSION: Cycle 1(5+8scouts, MP>=13) → Cycle 2(7+8scouts, MP>=15) → Cycle 3(9+8scouts, MP>=17) → Current({}, MP>={})'.format(
                expected_wave1, self.min_attack_mp))
            
        if self.ready_for_scout_rush:
            # Execute escalating scout rush sequence
            self.execute_escalating_scout_rush(game_state)

    def execute_escalating_scout_rush(self, game_state):
        """
        Execute the 3-phase ESCALATING scout rush with mandatory defense rebuilding
        """
        mp = int(game_state.get_resource(MP))  # Convert to integer to avoid float errors
        
        # Phase 1: Setup blocking turrets (uses ESCALATING MP threshold)
        if mp >= self.min_attack_mp and not self.turret_removed_for_attack:
            # REMOVE all turrets in blocking_turret_position2 to clear attack path
            turrets_removed = 0
            for location in self.blocking_turret_position2:
                if game_state.contains_stationary_unit(location):
                    game_state.attempt_remove([location])
                    turrets_removed += 1
                    gamelib.debug_write('PHASE 1: Removed blocking turret at {}'.format(location))
            
            # Set indicators - attack will happen NEXT turn
            self.turret_removed_for_attack = True
            self.attack_path_cleared = True
            gamelib.debug_write('PHASE 1: ESCALATING ATTACK PREP COMPLETE (Cycle {})'.format(self.attack_cycles_completed + 1))
            gamelib.debug_write('MP Threshold: {} | Turrets Removed: {} | MASSIVE scout wave incoming NEXT turn!'.format(
                self.min_attack_mp, turrets_removed))
            
            # DO NOT deploy scouts this turn - return immediately
            return
        
        # Phase 2: Deploy ESCALATING scout attack (attack turn)
        elif self.attack_path_cleared and self.turret_removed_for_attack:
            # Deploy scouts with ESCALATING wave sizes based on attack cycle progression
            available_mp = mp
            
            # ESCALATING WAVE 1: Increases by +2 scouts each attack cycle
            base_wave1_size = 5 + (self.attack_cycles_completed * 2)  # 5, 7, 9, 11, 13...
            wave1_scouts = min(base_wave1_size, available_mp)  # Don't exceed available MP
            remaining_mp_after_wave1 = available_mp - wave1_scouts
            wave2_scouts = max(remaining_mp_after_wave1, 0)  # Use ALL remaining MP for wave 2
            
            # Deploy Wave 1: scouts at position 1
            actual_wave1 = game_state.attempt_spawn(SCOUT, self.scout_attack_position1, wave1_scouts)
            
            # Deploy Wave 2: remaining scouts at position 2 (THIS IS THE ESCALATING PART!)
            actual_wave2 = game_state.attempt_spawn(SCOUT, self.scout_attack_position2, wave2_scouts)
            
            total_deployed = actual_wave1 + actual_wave2
            
            gamelib.debug_write('🌊 PHASE 2: DUAL ESCALATING WAVES DEPLOYED! 🌊')
            gamelib.debug_write('Attack Cycle: {} | MP Used: {}/{} | Wave 1: {} scouts (Base: {}) | Wave 2: {} scouts | TOTAL: {} SCOUTS'.format(
                self.attack_cycles_completed + 1, available_mp, available_mp, actual_wave1, base_wave1_size, actual_wave2, total_deployed))
            gamelib.debug_write('DUAL ESCALATION: Wave 1 grows by +2 scouts, MP threshold +2 each cycle!')
            gamelib.debug_write('NEXT ATTACK: Wave 1 will be {} scouts, MP threshold {}'.format(
                base_wave1_size + 2, self.min_attack_mp + 2))
            
            # Set flag for mandatory rebuild next turn
            self.attack_path_cleared = False  # Attack is complete, prepare for rebuild
            gamelib.debug_write('PHASE 2: Massive attack launched! Defenses will be rebuilt NEXT turn')
        
        # Phase 3: ALWAYS rebuild defenses AND increment escalation counter
        elif not self.attack_path_cleared and self.turret_removed_for_attack:
            # ALWAYS rebuild all turrets in blocking_turret_position2
            turrets_rebuilt = 0
            for location in self.blocking_turret_position2:
                if not game_state.contains_stationary_unit(location):
                    if game_state.can_spawn(TURRET, location):
                        game_state.attempt_spawn(TURRET, location)
                        turrets_rebuilt += 1
                        gamelib.debug_write('PHASE 3: Rebuilt blocking turret at {}'.format(location))
            
            # ESCALATION SYSTEM: Increase attack cycle counter and MP threshold
            previous_threshold = self.min_attack_mp
            self.attack_cycles_completed += 1
            self.min_attack_mp += 2  # CRITICAL: Increase threshold by 2 for next attack
            
            # Reset attack mode indicators to normal defensive state
            self.turret_removed_for_attack = False
            self.ready_for_scout_rush = False
            
            gamelib.debug_write('📈 PHASE 3: DUAL ESCALATION SYSTEM ACTIVATED! 📈')
            gamelib.debug_write('Attack Cycle {} COMPLETED | Turrets Rebuilt: {}'.format(
                self.attack_cycles_completed, turrets_rebuilt))
            gamelib.debug_write('DUAL ESCALATION: MP Threshold {} → {} (+2) | Next Wave 1: {} → {} scouts (+2)'.format(
                previous_threshold, self.min_attack_mp, 5 + ((self.attack_cycles_completed-1) * 2), 5 + (self.attack_cycles_completed * 2)))
            gamelib.debug_write('NEXT ATTACK: Will need MP>={} for Wave 1({} scouts) + Wave 2(remaining MP)'.format(
                self.min_attack_mp, 5 + (self.attack_cycles_completed * 2)))
            gamelib.debug_write('DUAL PROGRESSION: Cycle 1(5scouts+MP>=13) → Cycle 2(7scouts+MP>=15) → Cycle 3(9scouts+MP>=17) → Cycle 4(11scouts+MP>=19)...')


    def on_action_frame(self, turn_string):
        """
        Track where we get scored on for defensive analysis
        """
        state = json.loads(turn_string)
        events = state["events"]
        breaches = events["breach"]
        for breach in breaches:
            location = breach[0]
            unit_owner_self = True if breach[4] == 1 else False
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                self.scored_on_locations.append(location)


if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()