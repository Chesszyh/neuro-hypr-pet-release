import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shimeji_model import load_action_catalog, load_behavior_catalog
from src.sound import SoundEvent
from src.runtime import (
    BreedEvent,
    InteractionEvent,
    PetRuntime,
    PetWorld,
    RuntimeConfig,
    Rect,
    SelfDestructEvent,
    TransformEvent,
)


XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <ActionList>
    <Action Name="Look" Type="Embedded" Class="com.group_finity.mascot.action.Look"/>
    <Action Name="Nudge" Type="Embedded" Class="com.group_finity.mascot.action.Offset" X="7" Y="-3"/>
    <Action Name="Stand" Type="Stay" BorderType="Floor">
      <Animation>
        <Pose Image="/stand.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
        <Hotspot Shape="Ellipse" Origin="38,15" Size="48,26" Behavior="StandBlush"/>
      </Animation>
    </Action>
    <Action Name="StandBlush" Type="Stay" BorderType="Floor">
      <Animation>
        <Pose Image="/stand-blush.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="Walk" Type="Move" BorderType="Floor">
      <Animation>
        <Pose Image="/walk1.png" ImageAnchor="64,128" Velocity="-2,0" Duration="1"/>
        <Pose Image="/walk2.png" ImageAnchor="64,128" Velocity="-2,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="Run" Type="Move" BorderType="Floor">
      <Animation>
        <Pose Image="/run1.png" ImageAnchor="64,128" Velocity="-6,0" Duration="1"/>
        <Pose Image="/run2.png" ImageAnchor="64,128" Velocity="-6,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="TurnRun" Type="Move" BorderType="Floor">
      <Animation>
        <Pose Image="/turn-run.png" ImageAnchor="64,128" Velocity="-6,0" Duration="1"/>
      </Animation>
      <Animation IsTurn="true">
        <Pose Image="/turn.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="LegacyTurnWalk" Type="MoveWithTurn" BorderType="Floor">
      <Animation>
        <Pose Image="/legacy-walk.png" ImageAnchor="64,128" Velocity="-2,0" Duration="1"/>
      </Animation>
      <Animation>
        <Pose Image="/legacy-turn.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="EmbeddedLegacyTurnWalk" Type="Embedded" Class="com.group_finity.mascot.action.MoveWithTurn" BorderType="Floor">
      <Animation>
        <Pose Image="/embedded-legacy-walk.png" ImageAnchor="64,128" Velocity="-2,0" Duration="1"/>
      </Animation>
      <Animation>
        <Pose Image="/embedded-legacy-turn.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="RunAffordance" Type="Embedded" Class="com.group_finity.mascot.action.ScanMove" BorderType="Floor">
      <Animation>
        <Pose Image="/run-affordance1.png" ImageAnchor="64,128" Velocity="-8,0" Duration="1"/>
        <Pose Image="/run-affordance2.png" ImageAnchor="64,128" Velocity="-8,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="Falling" Type="Embedded" Class="com.group_finity.mascot.action.Fall" Gravity="2">
      <Animation>
        <Pose Image="/fall.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="HurledFall" Type="Embedded" Class="com.group_finity.mascot.action.Fall" Gravity="2">
      <Animation>
        <Pose Image="/hurled-fall.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="Jumping" Type="Embedded" Class="com.group_finity.mascot.action.Jump" VelocityParam="20">
      <Animation>
        <Pose Image="/jump.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="FallWithIe" Type="Embedded" Class="com.group_finity.mascot.action.FallWithIE" IeOffsetX="-1" IeOffsetY="-65">
      <Animation>
        <Pose Image="/fall-ie.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="WalkWithIe" Type="Embedded" Class="com.group_finity.mascot.action.WalkWithIE" BorderType="Floor" IeOffsetX="-1" IeOffsetY="-65">
      <Animation>
        <Pose Image="/walk-ie1.png" ImageAnchor="64,128" Velocity="-3,0" Duration="1"/>
        <Pose Image="/walk-ie2.png" ImageAnchor="64,128" Velocity="-3,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="ThrowIe" Type="Embedded" Class="com.group_finity.mascot.action.ThrowIE" InitialVX="32" InitialVY="-10" Gravity="0.5">
      <Animation>
        <Pose Image="/throw-ie.png" ImageAnchor="64,128" Velocity="0,0" Duration="4"/>
      </Animation>
    </Action>
    <Action Name="Bouncing" Type="Animate" BorderType="Floor">
      <Animation>
        <Pose Image="/bounce1.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
        <Pose Image="/bounce2.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="Tripping" Type="Animate" BorderType="Floor">
      <Animation>
        <Pose Image="/trip1.png" ImageAnchor="64,128" Velocity="-4,0" Duration="2"/>
        <Pose Image="/trip2.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="Sit" Type="Stay" BorderType="Floor">
      <Animation>
        <Pose Image="/sit.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="Sprawl" Type="Stay" BorderType="Floor">
      <Animation>
        <Pose Image="/sprawl.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="SitAndLookAtMouse" Type="Stay" BorderType="Floor">
      <Animation>
        <Pose Image="/sit-mouse.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="HeartHeartHeartAction" Type="Animate" BorderType="Floor">
      <Animation>
        <Pose Image="/heart1.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
        <Pose Image="/heart2.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="SoundAction" Type="Animate" BorderType="Floor">
      <Animation>
        <Pose Image="/sound1.png" ImageAnchor="64,128" Velocity="0,0" Duration="2" Sound="knock.wav" Volume="1"/>
        <Pose Image="/sound2.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="LoopStepA" Type="Animate" BorderType="Floor">
      <Animation>
        <Pose Image="/loop-a.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="LoopStepB" Type="Animate" BorderType="Floor">
      <Animation>
        <Pose Image="/loop-b.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="UntouchableAction" Type="Animate" BorderType="Floor" Draggable="false">
      <Animation>
        <Pose Image="/untouchable.png" ImageAnchor="64,128" Velocity="0,0" Duration="4"/>
      </Animation>
    </Action>
    <Action Name="TransformIntoTutel" Type="Embedded" Class="com.group_finity.mascot.action.Transform"
            TransformMascot="Tuteling" TransformBehavior="StandUp" BorderType="Floor">
      <Animation>
        <Pose Image="/transform1.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="SelfDestruct" Type="Embedded" Class="com.group_finity.mascot.action.SelfDestruct"
            BorderType="Floor">
      <Animation>
        <Pose Image="/self-destruct.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="BreedChild" Type="Embedded" Class="com.group_finity.mascot.action.Breed"
            BornX="16" BornY="-8" BornMascot="Tuteling Cursor" BornBehavior="ThrowIEFromLeft"
            BornTransient="true" BorderType="Floor">
      <Animation>
        <Pose Image="/breed.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="BreedRun" Type="Embedded" Class="com.group_finity.mascot.action.BreedMove"
            BornX="16" BornY="-8" BornInterval="1" BornBehavior="RunChild" BorderType="Floor">
      <Animation>
        <Pose Image="/breed-run.png" ImageAnchor="64,128" Velocity="-2,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="BreedLeap" Type="Embedded" Class="com.group_finity.mascot.action.BreedJump"
            BornX="16" BornY="-8" BornInterval="1" BornBehavior="LeapChild" VelocityParam="40">
      <Animation>
        <Pose Image="/breed-leap.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="GrabWall" Type="Stay" BorderType="Wall">
      <Animation>
        <Pose Image="/wall.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="ClimbWall" Type="Move" BorderType="Wall">
      <Animation Condition="#{TargetY &lt; mascot.anchor.y}">
        <Pose Image="/climb-wall-up.png" ImageAnchor="64,128" Velocity="0,-2" Duration="1"/>
      </Animation>
      <Animation Condition="#{TargetY &gt;= mascot.anchor.y}">
        <Pose Image="/climb-wall-down.png" ImageAnchor="64,128" Velocity="0,3" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="GrabCeiling" Type="Stay" BorderType="Ceiling">
      <Animation>
        <Pose Image="/ceiling.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="ClimbCeiling" Type="Move" BorderType="Ceiling">
      <Animation>
        <Pose Image="/climb-ceiling.png" ImageAnchor="64,128" Velocity="-2,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="ClimbIEWall" Type="Sequence" Loop="false">
      <ActionReference Name="ClimbWall" TargetY="#{mascot.environment.activeIE.top+64}"/>
    </Action>
    <Action Name="ClimbIEBottom" Type="Sequence" Loop="false">
      <ActionReference Name="ClimbCeiling" TargetX="#{mascot.environment.activeIE.left+64}"/>
    </Action>
    <Action Name="WalkAlongWorkAreaFloor" Type="Sequence" Loop="false">
      <ActionReference Name="Walk" TargetX="${mascot.environment.workArea.left+64}"/>
    </Action>
    <Action Name="RunAlongWorkAreaFloor" Type="Sequence" Loop="false">
      <ActionReference Name="Run" TargetX="${mascot.environment.workArea.left+64+Math.random()*(mascot.environment.workArea.width-128)}"/>
    </Action>
    <Action Name="DashTowardMouseWithGap" Type="Sequence" Loop="false">
      <ActionReference Name="Run" TargetX="#{mascot.environment.cursor.x+Gap}"
        Gap="${mascot.anchor.x &lt; mascot.environment.cursor.x ? -20 : 20}"/>
    </Action>
    <Action Name="EscapeLeftWallThenFall" Type="Sequence" Loop="false">
      <Action Type="Sequence" Condition="${mascot.environment.workArea.leftBorder.isOn(mascot.anchor)}">
        <ActionReference Name="Offset" X="1"/>
        <ActionReference Name="Falling" InitialVX="0" InitialVY="0"/>
      </Action>
      <ActionReference Name="Run" TargetX="200"/>
    </Action>
    <Action Name="SitDown" Type="Sequence" Loop="false">
      <ActionReference Name="Sit" Duration="4"/>
    </Action>
    <Action Name="LieDown" Type="Sequence" Loop="false">
      <ActionReference Name="Sprawl" Duration="4"/>
    </Action>
    <Action Name="HeartHeartHeart" Type="Sequence" Loop="false">
      <ActionReference Name="HeartHeartHeartAction"/>
    </Action>
    <Action Name="OffsetThenSit" Type="Sequence" Loop="false">
      <ActionReference Name="Offset" X="12" Y="-8"/>
      <ActionReference Name="Sit" Duration="4"/>
    </Action>
    <Action Name="LookThenWalkToTernaryTarget" Type="Sequence" Loop="false">
      <ActionReference Name="Look" LookRight="true"/>
      <ActionReference Name="Walk" TargetX="${mascot.lookRight ? mascot.environment.workArea.right-64 : mascot.environment.workArea.left+64}"/>
    </Action>
    <Action Name="SitAndFaceMouse" Type="Sequence" Loop="false">
      <ActionReference Name="SitAndLookAtMouse" Duration="2"/>
      <ActionReference Name="Look" LookRight="${mascot.anchor.x &lt; mascot.environment.cursor.x}"/>
    </Action>
    <Action Name="JumpFromIE" Type="Sequence" Loop="false">
      <ActionReference Name="Falling" InitialVX="-15" InitialVY="-20"/>
    </Action>
    <Action Name="JumpToPointThenSit" Type="Sequence" Loop="false">
      <ActionReference Name="Jumping" TargetX="200" TargetY="220"/>
      <ActionReference Name="Sit" Duration="4"/>
    </Action>
    <Action Name="ClimbWallThenStand" Type="Sequence" Loop="false">
      <ActionReference Name="ClimbWall" TargetY="#{mascot.environment.activeIE.top+64}"/>
      <ActionReference Name="Stand" Duration="5"/>
    </Action>
    <Action Name="FallThenStand" Type="Sequence" Loop="false">
      <ActionReference Name="Falling" InitialVX="0" InitialVY="0"/>
      <ActionReference Name="Stand" Duration="5"/>
    </Action>
    <Action Name="FallWithSelect" Type="Sequence" Loop="false">
      <ActionReference Name="Falling" InitialVX="0" InitialVY="0"/>
      <Action Type="Select">
        <Action Type="Sequence" Condition="${mascot.environment.floor.isOn(mascot.anchor)}">
          <ActionReference Name="Bouncing"/>
          <ActionReference Name="Stand" Duration="4"/>
        </Action>
        <ActionReference Name="GrabWall" Duration="100"/>
      </Action>
    </Action>
    <Action Name="CarryIeRightThenThrow" Type="Sequence" Loop="false">
      <ActionReference Name="WalkWithIe" TargetX="220"/>
      <ActionReference Name="ThrowIe"/>
      <ActionReference Name="Stand" Duration="4"/>
    </Action>
    <Action Name="LoopPair" Type="Sequence" Loop="true">
      <ActionReference Name="LoopStepA"/>
      <ActionReference Name="LoopStepB"/>
    </Action>
  </ActionList>
</Mascot>
"""


BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Condition Condition="#{mascot.environment.floor.isOn(mascot.anchor)}">
      <Behavior Name="SitDown" Frequency="25"/>
      <Behavior Name="LieDown" Frequency="75"/>
    </Condition>
    <Condition Condition="#{mascot.environment.workArea.topBorder.isOn(mascot.anchor)}">
      <Behavior Name="HeartHeartHeart" Frequency="90"/>
    </Condition>
  </BehaviorList>
</Mascot>
"""


TARGET_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <ActionList>
    <Action Name="Stand" Type="Stay" BorderType="Floor">
      <Animation>
        <Pose Image="/target-stand.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="StandUp" Type="Sequence" Loop="false">
      <ActionReference Name="Stand" Duration="4"/>
    </Action>
  </ActionList>
</Mascot>
"""


INTERACTION_XML = XML.replace(
    '<Action Name="RunAffordance" Type="Embedded" Class="com.group_finity.mascot.action.ScanMove" BorderType="Floor">',
    '<Action Name="RunAffordance" Type="Embedded" Class="com.group_finity.mascot.action.ScanMove" '
    'Affordance="Cuddle" Behavior="StandBlush" TargetBehavior="Stand" TargetLook="true" BorderType="Floor">',
).replace(
    '    <Action Name="Falling" Type="Embedded" Class="com.group_finity.mascot.action.Fall" Gravity="2">',
    '''    <Action Name="SitAffordance" Type="Animate" Affordance="Cuddle" BorderType="Floor">
      <Animation>
        <Pose Image="/sit-affordance.png" ImageAnchor="64,128" Velocity="0,0" Duration="50"/>
      </Animation>
    </Action>
    <Action Name="LeapAffordance" Type="Embedded" Class="com.group_finity.mascot.action.ScanJump"
            Affordance="Cuddle" Behavior="StandBlush" TargetBehavior="Stand" TargetLook="true" VelocityParam="40">
      <Animation>
        <Pose Image="/leap-affordance.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
    </Action>
    <Action Name="WaveAffordance" Type="Embedded" Class="com.group_finity.mascot.action.ScanInteract"
            Affordance="Cuddle" Behavior="StandBlush" TargetBehavior="Stand" TargetLook="true" BorderType="Floor">
      <Animation>
        <Pose Image="/wave-affordance.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="TurnWaveAffordance" Type="Embedded" Class="com.group_finity.mascot.action.ScanInteract"
            Affordance="Cuddle" Behavior="StandBlush" TargetBehavior="Stand" BorderType="Floor">
      <Animation>
        <Pose Image="/turn-wave-affordance.png" ImageAnchor="64,128" Velocity="0,0" Duration="1"/>
      </Animation>
      <Animation IsTurn="true">
        <Pose Image="/scan-interact-turn.png" ImageAnchor="64,128" Velocity="0,0" Duration="2"/>
      </Animation>
    </Action>
    <Action Name="Falling" Type="Embedded" Class="com.group_finity.mascot.action.Fall" Gravity="2">''',
)


RICH_BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Behavior Name="SitAndFaceMouse" Frequency="10"/>
    <Condition Condition="#{mascot.environment.activeIE.visible}">
      <Behavior Name="WalkAlongWorkAreaFloor" Frequency="40"
        Condition="#{mascot.anchor.x &lt; mascot.environment.activeIE.left &amp;&amp;
          Math.abs(mascot.environment.activeIE.bottom-mascot.anchor.y) &lt; mascot.environment.activeIE.height/4}"/>
    </Condition>
  </BehaviorList>
</Mascot>
"""


NEXT_BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Condition Condition="#{mascot.environment.floor.isOn(mascot.anchor)}">
      <Behavior Name="StandUp" Frequency="10"/>
      <Behavior Name="SitDown" Frequency="25">
        <NextBehaviorList Add="true">
          <BehaviorReference Name="LieDown" Frequency="100"/>
        </NextBehaviorList>
      </Behavior>
      <Behavior Name="LieDown" Frequency="75">
        <NextBehaviorList Add="false">
          <BehaviorReference Name="HeartHeartHeart" Frequency="5"
            Condition="#{mascot.environment.workArea.topBorder.isOn(mascot.anchor)}"/>
          <BehaviorReference Name="SitDown" Frequency="7"
            Condition="#{mascot.environment.workArea.bottomBorder.isOn(mascot.anchor)}"/>
        </NextBehaviorList>
      </Behavior>
    </Condition>
  </BehaviorList>
</Mascot>
"""


INSTANT_END_NEXT_BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Behavior Name="SitAndFaceMouse" Frequency="10">
      <NextBehaviorList Add="false">
        <BehaviorReference Name="LieDown" Frequency="1"/>
      </NextBehaviorList>
    </Behavior>
    <Behavior Name="LieDown" Frequency="1"/>
  </BehaviorList>
</Mascot>
"""


ACTION_ALIAS_BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Behavior Name="PretendLie" Action="LieDown" Frequency="100"/>
    <Behavior Name="PretendSit" Action="SitDown" Frequency="1">
      <NextBehaviorList Add="false">
        <BehaviorReference Name="PretendLieNext" Action="LieDown" Frequency="1"/>
      </NextBehaviorList>
    </Behavior>
  </BehaviorList>
</Mascot>
"""


TOTAL_COUNT_BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Behavior Name="BreedChild" Frequency="100" Condition="#{mascot.totalCount &lt; 2}"/>
  </BehaviorList>
</Mascot>
"""


class ShimejiRuntimeTest(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_neuron_breeding_stays_rare_and_stops_at_six_pets(self) -> None:
        image_set = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf"
        catalog = load_action_catalog(image_set / "actions.xml")
        behaviors = load_behavior_catalog(image_set / "behaviors.xml")
        world = PetWorld()
        runtimes = [
            PetRuntime(catalog, RuntimeConfig(Rect(0, 0, 800, 600), 400, 600), behaviors)
            for _ in range(6)
        ]
        world.register(runtimes[0])

        candidates = {name: weight for name, _action, weight in runtimes[0]._weighted_behavior_candidates()}
        self.assertEqual(candidates["SplitIntoTwo"], 5)
        self.assertEqual(candidates["Gymbag"], 5)

        for runtime in runtimes[1:]:
            world.register(runtime)
        candidates = {name: weight for name, _action, weight in runtimes[0]._weighted_behavior_candidates()}
        self.assertNotIn("SplitIntoTwo", candidates)
        self.assertNotIn("Gymbag", candidates)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_eviling_breeding_stays_rare_with_companions_present(self) -> None:
        image_set = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Eviling/conf"
        catalog = load_action_catalog(image_set / "actions.xml")
        behaviors = load_behavior_catalog(image_set / "behaviors.xml")
        world = PetWorld()
        runtimes = [
            PetRuntime(catalog, RuntimeConfig(Rect(0, 0, 800, 600), 400, 600), behaviors)
            for _ in range(6)
        ]
        world.register(runtimes[0])

        candidates = {name: weight for name, _action, weight in runtimes[0]._weighted_behavior_candidates()}
        self.assertEqual(candidates["NewClone"], 5)
        self.assertEqual(candidates["PullUpShimeji"], 5)
        self.assertEqual(candidates["FrickOffAndDisappear"], 3)

        for runtime in runtimes[1:]:
            world.register(runtime)
        candidates = {name: weight for name, _action, weight in runtimes[0]._weighted_behavior_candidates()}
        self.assertNotIn("NewClone", candidates)
        self.assertNotIn("PullUpShimeji", candidates)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_world_treats_vedaling_as_same_tutel_companion_after_transform(self) -> None:
        collection = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img"
        tutel = collection / "Tuteling/conf"
        vedal = collection / "Vedaling/conf"
        runtime = PetRuntime(
            load_action_catalog(tutel / "actions.xml"),
            RuntimeConfig(Rect(0, 0, 800, 600), 400, 600),
            load_behavior_catalog(tutel / "behaviors.xml"),
        )
        world = PetWorld()
        world.register(runtime)
        self.assertTrue(world.has_image_set("Tuteling", "Vedaling"))

        runtime.apply_transform(
            load_action_catalog(vedal / "actions.xml"),
            load_behavior_catalog(vedal / "behaviors.xml"),
            "LieDown",
        )

        self.assertTrue(world.has_image_set("Tuteling", "Vedaling"))
        self.assertFalse(world.has_image_set("Tuteling"))

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_neuron_and_eviling_native_hug_uses_companion_affordance(self) -> None:
        collection = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img"

        def make_pet(image_set: str, x: int) -> PetRuntime:
            conf = collection / image_set / "conf"
            runtime = PetRuntime(
                load_action_catalog(conf / "actions.xml"),
                RuntimeConfig(Rect(0, 0, 800, 600), x, 600),
                load_behavior_catalog(conf / "behaviors.xml"),
            )
            runtime.start_action("Stand")
            return runtime

        neuro = make_pet("Neuron", 240)
        evil = make_pet("Eviling", 480)
        world = PetWorld()
        world.register(neuro)
        world.register(evil)
        evil.start_action("SitAffordance")
        neuro.start_action("HugEvil")

        for _ in range(150):
            neuro.tick()
            evil.tick()
            for event in neuro.pop_interaction_events():
                event.target.start_action(event.target_behavior)
            if neuro.action_name == "HugAction":
                break

        self.assertEqual(neuro.action_name, "HugAction")
        self.assertEqual(evil.action_name, "HuggedAction")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_manual_behaviors_use_visible_native_actions_and_current_conditions(self) -> None:
        image_set = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf"
        runtime = PetRuntime(
            load_action_catalog(image_set / "actions.xml"),
            RuntimeConfig(Rect(0, 0, 800, 600), 400, 600),
            load_behavior_catalog(image_set / "behaviors.xml"),
        )
        world = PetWorld()
        world.register(runtime)

        names = runtime.available_manual_behaviors()
        self.assertIn("SitDown", names)
        self.assertIn("Wink", names)
        self.assertIn("SplitIntoTwo", names)
        self.assertNotIn("Dragged", names)
        self.assertNotIn("ClimbAlongCeiling", names)
        self.assertNotIn("HugEvil", names)
        self.assertNotIn("NoticeFallingTutel", names)
        self.assertFalse(runtime.start_manual_behavior("Dragged"))
        self.assertTrue(runtime.start_manual_behavior("Wink"))
        self.assertNotEqual(runtime.action_name, "Stand")

        collection = image_set.parents[1]
        for image_set_name in ("Eviling", "Tuteling"):
            conf = collection / image_set_name / "conf"
            companion = PetRuntime(
                load_action_catalog(conf / "actions.xml"),
                RuntimeConfig(Rect(0, 0, 800, 600), 500, 600),
                load_behavior_catalog(conf / "behaviors.xml"),
            )
            world.register(companion)
        names = runtime.available_manual_behaviors()
        self.assertIn("HugEvil", names)
        self.assertIn("NoticeFallingTutel", names)

    def test_load_action_catalog_reads_pose_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        walk = catalog.actions["Walk"]
        self.assertEqual(walk.kind, "Move")
        self.assertEqual(len(walk.frames), 2)
        self.assertEqual(walk.frames[0].image, "walk1.png")
        self.assertEqual((walk.frames[0].anchor_x, walk.frames[0].anchor_y), (64, 128))
        self.assertEqual((walk.frames[0].velocity_x, walk.frames[0].velocity_y), (-2.0, 0.0))
        self.assertEqual(walk.frames[0].duration, 1)

    def test_runtime_falls_until_floor_then_stands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=0))

            for _ in range(80):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 240)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_direct_instant_actions_apply_and_return_to_stand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.start_action("Look")
            runtime.start_action("Nudge")

        self.assertTrue(runtime.look_right)
        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (167, 237))
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_walk_moves_in_facing_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.start_action("Walk", look_right=True, target_x=168)
            for _ in range(8):
                runtime.tick()

        self.assertEqual(runtime.anchor_x, 168)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_timed_floor_action_applies_pose_velocity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.start_action("Tripping", look_right=True, duration=4)
            runtime.tick()

        self.assertEqual(runtime.anchor_x, 164)
        self.assertEqual(runtime.anchor_y, 240)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_floor_move_respects_zero_velocity_pose(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=400, start_y=1080))

        runtime.start_action("Creep", look_right=True, target_x=500)
        runtime.tick()

        self.assertEqual(runtime.action_name, "Creep")
        self.assertEqual(runtime.frame.image, "shime20.png")
        self.assertEqual(runtime.anchor_x, 400)

    def test_runtime_reports_current_sprite_rect_from_anchor_and_png_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            rect = runtime.sprite_rect(128, 128)

        self.assertEqual(rect, Rect(96, 112, 128, 128))
        self.assertTrue(rect.contains(160, 200))
        self.assertFalse(rect.contains(95, 200))

    def test_runtime_drag_updates_anchor_only_after_sprite_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            self.assertFalse(runtime.pointer_down(20, 20, image_width=128, image_height=128))
            self.assertFalse(runtime.dragging)

            self.assertTrue(runtime.pointer_down(170, 230, image_width=128, image_height=128))
        self.assertTrue(runtime.dragging)
        self.assertTrue(runtime.pointer_motion(210, 200))

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (200, 210))

    def test_runtime_pointer_down_on_non_draggable_action_does_not_start_dragging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.start_action("UntouchableAction", duration=4)
            handled = runtime.pointer_down(170, 230, image_width=128, image_height=128)

        self.assertTrue(handled)
        self.assertFalse(runtime.dragging)
        self.assertEqual(runtime.action_name, "UntouchableAction")

    def test_runtime_click_on_hotspot_starts_behavior_on_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            handled = runtime.pointer_down(158, 140, image_width=128, image_height=128)
            self.assertEqual(runtime.action_name, "Stand")
            self.assertTrue(runtime.pointer_active)
            self.assertFalse(runtime.pointer_motion(160, 141))
            self.assertTrue(runtime.pointer_up(160, 141))

        self.assertTrue(handled)
        self.assertFalse(runtime.dragging)
        self.assertEqual(runtime.action_name, "StandBlush")

    def test_runtime_drag_from_hotspot_takes_precedence_over_click_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            runtime = PetRuntime(
                load_action_catalog(xml_path),
                RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240),
            )

            self.assertTrue(runtime.pointer_down(158, 140, image_width=128, image_height=128))
            self.assertTrue(runtime.pointer_motion(180, 140))
            self.assertTrue(runtime.dragging)
            self.assertEqual(runtime.action_name, "Stand")
            self.assertTrue(runtime.pointer_up(180, 140))
            self.assertFalse(runtime.pointer_active)
            self.assertNotEqual(runtime.action_name, "StandBlush")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_vedal_head_can_be_dragged_or_patted(self) -> None:
        conf = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Vedaling/conf"
        catalog = load_action_catalog(conf / "actions.xml")
        runtime = PetRuntime(catalog, RuntimeConfig(Rect(0, 0, 800, 600), 400, 600))
        head_x, head_y = 400, 490

        self.assertTrue(runtime.pointer_down(head_x, head_y, image_width=128, image_height=128))
        self.assertTrue(runtime.pointer_motion(head_x + 30, head_y))
        self.assertTrue(runtime.dragging)
        self.assertEqual(runtime.action_name, "Pinched")
        self.assertTrue(runtime.pointer_up(head_x + 30, head_y))

        runtime.anchor_x = 400
        runtime.anchor_y = 600
        runtime.start_action("Stand")
        self.assertTrue(runtime.pointer_down(head_x, head_y, image_width=128, image_height=128))
        self.assertTrue(runtime.pointer_up(head_x, head_y))
        self.assertEqual(runtime.action_name, "StandingBlush")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_tutel_shell_click_still_allows_dragging(self) -> None:
        conf = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Tuteling/conf"
        runtime = PetRuntime(
            load_action_catalog(conf / "actions.xml"),
            RuntimeConfig(Rect(0, 0, 800, 600), 400, 600),
        )
        head_x, head_y = 380, 575

        self.assertTrue(runtime.pointer_down(head_x, head_y, image_width=128, image_height=128))
        self.assertTrue(runtime.pointer_motion(head_x + 20, head_y - 10))
        self.assertTrue(runtime.dragging)
        self.assertNotEqual(runtime.action_name, "StandActionBlush")
        self.assertTrue(runtime.pointer_up(head_x + 20, head_y - 10))

        runtime.anchor_x = 400
        runtime.anchor_y = 600
        runtime.start_action("Stand")
        self.assertTrue(runtime.pointer_down(head_x, head_y, image_width=128, image_height=128))
        self.assertTrue(runtime.pointer_up(head_x, head_y))
        self.assertEqual(runtime.action_name, "StandActionBlush")

    def test_runtime_hotspot_hit_testing_mirrors_when_looking_right(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.look_right = True
            handled = runtime.pointer_down(162, 140, image_width=128, image_height=128)
            runtime.pointer_up(162, 140)

        self.assertTrue(handled)
        self.assertFalse(runtime.dragging)
        self.assertEqual(runtime.action_name, "StandBlush")

    def test_runtime_release_after_drag_starts_falling_with_throw_velocity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.pointer_down(170, 230, image_width=128, image_height=128)
            runtime.pointer_motion(190, 220)
            runtime.pointer_motion(205, 210)
            self.assertTrue(runtime.pointer_up(205, 210))

        self.assertEqual(runtime.action_name, "Falling")
        self.assertGreater(runtime.velocity_x, 0)
        self.assertLess(runtime.velocity_y, 0)

    def test_runtime_release_uses_smoothed_throw_velocity_not_only_last_pointer_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 400, 260), start_x=160, start_y=240))

            runtime.pointer_down(170, 230, image_width=128, image_height=128)
            runtime.pointer_motion(230, 200)
            runtime.pointer_motion(232, 198)
            runtime.pointer_up(232, 198)

        self.assertEqual(runtime.action_name, "Falling")
        self.assertGreater(runtime.velocity_x, 8)
        self.assertLess(runtime.velocity_x, 35)
        self.assertLess(runtime.velocity_y, 0)

    def test_runtime_release_does_not_apply_late_reverse_cursor_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 400, 260), start_x=160, start_y=240))

            runtime.pointer_down(170, 230, image_width=128, image_height=128)
            runtime.pointer_motion(230, 200)
            self.assertTrue(runtime.pointer_up(130, 240))

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (220, 210))
        self.assertEqual(runtime.action_name, "Falling")
        self.assertGreater(runtime.velocity_x, 0)
        self.assertLess(runtime.velocity_y, 0)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_dragged_action_uses_smoothed_foot_x_for_pinched_animation(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        runtime.update_cursor_pos(960, 1000)
        self.assertTrue(runtime.pointer_down(960, 1000, image_width=128, image_height=128))
        runtime.update_cursor_pos(1050, 1000)
        runtime.pointer_motion(1050, 1000)
        runtime.tick()

        self.assertEqual(runtime.action_name, "Pinched")
        self.assertEqual(runtime.frame.image, "shime9.png")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_dragged_action_uses_shimeji_ee_cursor_anchor_offset(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        runtime.update_cursor_pos(960, 1000)
        self.assertTrue(runtime.pointer_down(960, 1000, image_width=128, image_height=128))
        runtime.pointer_motion(1000, 910)

        self.assertEqual(runtime.action_name, "Pinched")
        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (1000, 1030))

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_dragged_sequence_reaches_resisting_when_held_still(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        runtime.update_cursor_pos(960, 1000)
        self.assertTrue(runtime.pointer_down(960, 1000, image_width=128, image_height=128))
        with patch("src.runtime.random.random", return_value=0.0):
            for _ in range(250):
                runtime.tick()

        self.assertTrue(runtime.dragging)
        self.assertEqual(runtime.action_name, "Resisting")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_dragged_sequence_can_delay_resisting_like_shimeji_ee(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        runtime.update_cursor_pos(960, 1000)
        self.assertTrue(runtime.pointer_down(960, 1000, image_width=128, image_height=128))
        with patch("src.runtime.random.random", return_value=0.9):
            for _ in range(250):
                runtime.tick()

        self.assertTrue(runtime.dragging)
        self.assertEqual(runtime.action_name, "Pinched")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_dragged_sequence_loops_back_to_pinched_when_resisting_cursor_moves(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        runtime.update_cursor_pos(960, 1000)
        self.assertTrue(runtime.pointer_down(960, 1000, image_width=128, image_height=128))
        with patch("src.runtime.random.random", return_value=0.0):
            for _ in range(250):
                runtime.tick()
        self.assertEqual(runtime.action_name, "Resisting")

        runtime.update_cursor_pos(1030, 1000)
        runtime.pointer_motion(1030, 1000)

        self.assertEqual(runtime.action_name, "Pinched")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_regist_action_keeps_drag_control_after_animation_while_button_is_held(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        runtime.update_cursor_pos(960, 1000)
        self.assertTrue(runtime.pointer_down(960, 1000, image_width=128, image_height=128))
        with patch("src.runtime.random.random", return_value=0.0):
            for _ in range(250):
                runtime.tick()
        self.assertEqual(runtime.action_name, "Resisting")

        for _ in range(sum(frame.duration for frame in catalog.actions["Resisting"].frames)):
            runtime.tick()

        self.assertTrue(runtime.dragging)
        self.assertEqual(runtime.action_name, "Pinched")
        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (960, 1080))

    def test_runtime_thrown_pet_bounces_once_after_landing_before_standing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=240))

            runtime.pointer_down(170, 230, image_width=128, image_height=128)
            runtime.pointer_motion(180, 110)
            runtime.pointer_motion(185, 205)
            runtime.pointer_up(185, 205)
            for _ in range(120):
                runtime.tick()
                if runtime.action_name != "Falling":
                    break

            self.assertEqual(runtime.anchor_y, 240)
            self.assertEqual(runtime.action_name, "Bouncing")

            for _ in range(8):
                runtime.tick()

        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_falls_onto_active_window_top(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=160, start_y=0))

            runtime.update_active_window_rect(Rect(80, 100, 160, 80))
            for _ in range(80):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 100)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_uses_nearby_nonfocused_window_for_top_wall_and_bottom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 500, 300), start_x=360, start_y=0))
            windows = [Rect(60, 80, 140, 120), Rect(300, 120, 140, 120)]

            runtime.update_window_rects(windows)
            for _ in range(80):
                runtime.tick()
            self.assertEqual(runtime.anchor_y, 120)
            self.assertEqual(runtime.active_window_rect, windows[1])
            self.assertEqual(runtime.active_window_edge(), "top")

            runtime.anchor_x = 300
            runtime.anchor_y = 180
            self.assertEqual(runtime.active_window_edge(), "left")
            runtime.anchor_x = 360
            runtime.anchor_y = 240
            self.assertEqual(runtime.active_window_edge(), "bottom")

    def test_floating_window_top_takes_precedence_over_focused_tiled_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 500, 300), start_x=350, start_y=0))

            runtime.update_window_rects([Rect(300, 120, 120, 100), Rect(0, 35, 500, 265)], floating_count=1)
            for _ in range(80):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 120)

    def test_runtime_ignores_active_window_top_when_anchor_is_outside_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=40, start_y=0))

            runtime.update_active_window_rect(Rect(80, 100, 160, 80))
            for _ in range(80):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 240)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_walks_on_active_window_top_without_snapping_to_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=100, start_y=100))

            runtime.update_active_window_rect(Rect(80, 100, 160, 80))
            runtime.start_action("Walk", look_right=True, target_x=108)
            for _ in range(4):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 100)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_stays_attached_when_active_window_top_moves_slightly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=120, start_y=100))

            runtime.update_active_window_rect(Rect(80, 100, 160, 80))
            runtime.start_action("Stand")
            runtime.update_active_window_rect(Rect(80, 118, 160, 80))
            runtime.tick()

        self.assertEqual(runtime.anchor_y, 118)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_classifies_active_window_edges_near_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=100, start_y=100))

            runtime.update_active_window_rect(Rect(80, 100, 160, 80))
            self.assertEqual(runtime.active_window_edge(), "top")

            runtime.anchor_x = 80
            runtime.anchor_y = 140
            self.assertEqual(runtime.active_window_edge(), "left")

            runtime.anchor_x = 240
            runtime.anchor_y = 140
            self.assertEqual(runtime.active_window_edge(), "right")

            runtime.anchor_x = 120
            runtime.anchor_y = 180
            self.assertEqual(runtime.active_window_edge(), "bottom")

            runtime.anchor_x = 40
            runtime.anchor_y = 40
            self.assertEqual(runtime.active_window_edge(), "none")

    def test_runtime_edge_classification_has_tolerance_for_motion_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=78, start_y=140))

            runtime.update_active_window_rect(Rect(80, 100, 160, 80))

        self.assertEqual(runtime.active_window_edge(tolerance=3), "left")

    def test_runtime_falling_grabs_active_window_left_wall_on_horizontal_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=70, start_y=120))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.velocity_x = 40
            runtime.velocity_y = 0
            runtime.tick()

        self.assertEqual(runtime.anchor_x, 100)
        self.assertEqual(runtime.active_window_edge(tolerance=3), "left")
        self.assertEqual(runtime.action_name, "GrabWall")

    def test_runtime_falling_grabs_second_window_wall_even_before_nearest_window_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 400, 260), start_x=150, start_y=150))
            first = Rect(0, 80, 100, 120)
            second = Rect(200, 80, 100, 120)

            runtime.update_window_rects([first, second])
            self.assertEqual(runtime.active_window_rect, first)
            runtime.velocity_x = 70
            runtime.tick()

        self.assertEqual(runtime.anchor_x, second.left)
        self.assertEqual(runtime.active_window_rect, second)
        self.assertEqual(runtime.action_name, "GrabWall")

    def test_runtime_falling_grabs_active_window_right_wall_on_horizontal_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 240), start_x=230, start_y=120))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.velocity_x = -40
            runtime.velocity_y = 0
            runtime.tick()

        self.assertEqual(runtime.anchor_x, 200)
        self.assertEqual(runtime.active_window_edge(tolerance=3), "right")
        self.assertEqual(runtime.action_name, "GrabWall")

    def test_runtime_falling_grabs_active_window_bottom_when_thrown_upward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=220))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.velocity_x = 0
            runtime.velocity_y = -50
            runtime.tick()

        self.assertEqual(runtime.anchor_y, 180)
        self.assertEqual(runtime.active_window_edge(tolerance=3), "bottom")
        self.assertEqual(runtime.action_name, "GrabCeiling")

    def test_runtime_falling_grabs_work_area_left_edge_when_thrown_to_screen_border(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=18, start_y=120))

            runtime.velocity_x = -30
            runtime.velocity_y = 0
            runtime.tick()

        self.assertEqual(runtime.anchor_x, 0)
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.action_name, "GrabWall")

    def test_runtime_work_area_wall_grab_at_bottom_corner_stays_attached_before_climbing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=18, start_y=258))

            runtime.velocity_x = -30
            runtime.velocity_y = 0
            runtime.tick()
            self.assertEqual(runtime.action_name, "GrabWall")

            runtime.tick()

        self.assertEqual(runtime.action_name, "ClimbWall")
        self.assertEqual(runtime.target_y, 0)

    def test_runtime_falling_grabs_work_area_top_edge_when_thrown_upward_to_screen_border(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=20))

            runtime.velocity_x = 0
            runtime.velocity_y = -35
            runtime.tick()

        self.assertEqual(runtime.anchor_y, 0)
        self.assertEqual(runtime.action_name, "GrabCeiling")

    def test_runtime_climbs_active_window_wall_toward_target_y(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=100, start_y=160))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("ClimbWall", target_y=150)
            for _ in range(8):
                runtime.tick()

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (100, 150))
        self.assertEqual(runtime.action_name, "GrabWall")

    def test_runtime_wall_move_selects_animation_matching_target_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=0, start_y=160))

            runtime.start_action("ClimbWall", target_y=166)
            selected_before_tick = runtime.frame.image
            runtime.tick()

        self.assertEqual(selected_before_tick, "climb-wall-down.png")
        self.assertEqual(runtime.anchor_y, 163)

    def test_runtime_climbs_active_window_bottom_toward_target_x(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=180))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("ClimbCeiling", target_x=140)
            for _ in range(8):
                runtime.tick()

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (140, 180))
        self.assertEqual(runtime.action_name, "GrabCeiling")

    def test_runtime_falls_when_climbing_leaves_active_window_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=100, start_y=160))

            runtime.update_active_window_rect(None)
            runtime.start_action("ClimbWall", target_y=150)
            runtime.tick()

        self.assertEqual(runtime.action_name, "Falling")

    def test_runtime_grab_wall_auto_starts_climbing_toward_window_top(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=100, start_y=160))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("GrabWall")
            runtime.tick()

        self.assertEqual(runtime.action_name, "ClimbWall")
        self.assertEqual(runtime.target_y, 80)

    def test_runtime_grab_ceiling_auto_starts_climbing_toward_window_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=180))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("GrabCeiling")
            runtime.tick()

        self.assertEqual(runtime.action_name, "ClimbCeiling")
        self.assertEqual(runtime.target_x, 100)

    def test_runtime_sequence_starts_first_action_reference_with_active_window_target_y(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=100, start_y=160))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("ClimbIEWall")

        self.assertEqual(runtime.action_name, "ClimbWall")
        self.assertEqual(runtime.target_y, 144)

    def test_runtime_sequence_starts_first_action_reference_with_active_window_target_x(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=180))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("ClimbIEBottom")

        self.assertEqual(runtime.action_name, "ClimbCeiling")
        self.assertEqual(runtime.target_x, 164)

    def test_runtime_sequence_applies_initial_velocity_to_falling_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=100))

            runtime.start_action("JumpFromIE")

        self.assertEqual(runtime.action_name, "Falling")
        self.assertEqual(runtime.velocity_x, -15)
        self.assertEqual(runtime.velocity_y, -20)

    def test_runtime_falling_faces_horizontal_velocity_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=100))

            runtime.start_action("Falling")
            runtime.look_right = False
            runtime.velocity_x = 12
            runtime.tick()
            look_after_positive_velocity = runtime.look_right

            runtime.look_right = True
            runtime.velocity_x = -12
            runtime.tick()

        self.assertTrue(look_after_positive_velocity)
        self.assertFalse(runtime.look_right)

    def test_runtime_falling_accumulates_fractional_horizontal_velocity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=100))

            runtime.start_action("Falling")
            runtime.velocity_x = 0.6
            runtime.tick()
            x_after_first_tick = runtime.anchor_x
            runtime.tick()

        self.assertEqual(x_after_first_tick, 150)
        self.assertEqual(runtime.anchor_x, 151)

    def test_runtime_falling_does_not_clamp_velocity_like_shimeji_ee(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=120))

            runtime.start_action("Falling")
            runtime.velocity_x = 50.0
            runtime.velocity_y = 0.0
            runtime.tick()

        self.assertAlmostEqual(runtime.velocity_x, 47.5)

    def test_runtime_embedded_fall_class_keeps_custom_action_name_while_falling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=150, start_y=100))

            runtime.start_action("HurledFall")
            runtime.velocity_x = 10
            runtime.tick()

        self.assertEqual(runtime.action_name, "HurledFall")
        self.assertEqual(runtime.frame.image, "hurled-fall.png")
        self.assertGreater(runtime.anchor_x, 150)

    def test_runtime_jump_reference_moves_to_target_without_falling_and_continues_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("JumpToPointThenSit")
            self.assertEqual(runtime.action_name, "Jumping")
            for _ in range(20):
                runtime.tick()
                if runtime.action_name != "Jumping":
                    break

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (200, 220))
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.action_name, "Sit")

    def test_runtime_jump_step_uses_java_integer_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("Jumping", target_x=200, target_y=220)
            runtime.tick()

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (171, 244))

    def test_runtime_sequence_continues_to_next_reference_after_wall_move_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=100, start_y=160))

            runtime.update_active_window_rect(Rect(100, 80, 100, 100))
            runtime.start_action("ClimbWallThenStand")
            for _ in range(8):
                runtime.tick()

        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_sequence_continues_to_next_reference_after_falling_lands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 120), start_x=100, start_y=0))

            runtime.start_action("FallThenStand")
            for _ in range(80):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 120)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_loop_sequence_restarts_after_last_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("LoopPair")
            first_action = runtime.action_name
            runtime.tick()
            second_action = runtime.action_name
            runtime.tick()

        self.assertEqual(first_action, "LoopStepA")
        self.assertEqual(second_action, "LoopStepB")
        self.assertEqual(runtime.action_name, "LoopStepA")

    def test_runtime_select_executes_only_first_effective_branch_after_falling_lands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=0))

            runtime.start_action("FallWithSelect")
            for _ in range(120):
                runtime.tick()
                if runtime.action_name == "Bouncing":
                    break
            for _ in range(8):
                runtime.tick()

        self.assertEqual(runtime.anchor_y, 260)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_sequence_applies_offset_reference_and_continues_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("OffsetThenSit")

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (172, 252))
        self.assertEqual(runtime.action_name, "Sit")

    def test_runtime_sequence_applies_look_reference_before_ternary_target_expression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(20, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("LookThenWalkToTernaryTarget")

        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.action_name, "Walk")
        self.assertEqual(runtime.target_x, 276)

    def test_runtime_sequence_can_face_current_cursor_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.update_cursor_pos(220, 180)
            runtime.start_action("SitAndFaceMouse")
            for _ in range(3):
                runtime.tick()

        self.assertTrue(runtime.look_right)

    def test_runtime_cursor_delta_is_available_to_action_expressions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.update_cursor_pos(200, 180)
            runtime.update_cursor_pos(215, 170)

        self.assertEqual(runtime._resolve_int_param("${mascot.environment.cursor.dx}"), 15)
        self.assertEqual(runtime._resolve_int_param("${mascot.environment.cursor.dy}"), -10)

    def test_runtime_resolves_work_area_target_expressions_for_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(20, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("WalkAlongWorkAreaFloor")

        self.assertEqual(runtime.action_name, "Walk")
        self.assertEqual(runtime.target_x, 84)

    def test_runtime_run_sequence_uses_random_target_and_moves_toward_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=64, start_y=260))

            with patch("src.runtime.random.random", return_value=0.5):
                runtime.start_action("RunAlongWorkAreaFloor")
            runtime.tick()

        self.assertEqual(runtime.action_name, "Run")
        self.assertEqual(runtime.target_x, 160)
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.anchor_x, 70)

    def test_runtime_floor_sequence_skips_run_when_target_is_current_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.update_cursor_pos(180, 220)
            runtime.start_action("DashTowardMouseWithGap")

        self.assertEqual(runtime.action_name, "Stand")
        self.assertIsNone(runtime.target_x)
        self.assertEqual(runtime.anchor_x, 160)

    def test_runtime_floor_run_without_target_stops_at_work_area_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=3, start_y=260))

            runtime.start_action("Run", look_right=False)
            runtime.tick()

        self.assertEqual(runtime.anchor_x, 0)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_floor_run_near_bottom_snaps_to_floor_and_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=259))

            runtime.start_action("Run", look_right=True, target_x=200)
            runtime.tick()

        self.assertEqual(runtime.action_name, "Run")
        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (166, 260))

    def test_runtime_move_plays_turn_animation_before_moving_when_target_reverses_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.look_right = False
            runtime.start_action("TurnRun", target_x=190)
            first_frame = runtime.frame.image
            runtime.tick()
            x_after_first_tick = runtime.anchor_x
            frame_after_first_tick = runtime.frame.image
            runtime.tick()
            x_after_second_tick = runtime.anchor_x
            frame_after_second_tick = runtime.frame.image
            runtime.tick()

        self.assertTrue(runtime.look_right)
        self.assertEqual(first_frame, "turn.png")
        self.assertEqual(x_after_first_tick, 160)
        self.assertEqual(frame_after_first_tick, "turn.png")
        self.assertEqual(x_after_second_tick, 160)
        self.assertEqual(frame_after_second_tick, "turn-run.png")
        self.assertEqual(runtime.anchor_x, 166)

    def test_runtime_legacy_move_with_turn_uses_floor_move_target_semantics(self) -> None:
        for action_name in ("LegacyTurnWalk", "EmbeddedLegacyTurnWalk"):
            with self.subTest(action=action_name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    xml_path = root / "actions.xml"
                    xml_path.write_text(XML, encoding="utf-8")
                    catalog = load_action_catalog(xml_path)
                    runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

                    runtime.start_action(action_name, target_x=164)
                    runtime.tick()
                    runtime.tick()
                    runtime.tick()

                self.assertEqual(runtime.anchor_x, 164)
                self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_emits_sound_event_once_when_entering_pose_with_sound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("SoundAction", duration=4)
            self.assertEqual(runtime.pop_sound_events(), [])
            runtime.tick()
            first_events = runtime.pop_sound_events()
            runtime.tick()
            second_events = runtime.pop_sound_events()
            runtime.tick()
            third_events = runtime.pop_sound_events()
            runtime.tick()
            fourth_events = runtime.pop_sound_events()

        self.assertEqual(first_events, [SoundEvent("knock.wav", 1.0)])
        self.assertEqual(second_events, [])
        self.assertEqual(third_events, [])
        self.assertEqual(fourth_events, [SoundEvent("knock.wav", 1.0)])

    def test_runtime_transform_action_emits_event_after_animation_and_can_apply_target_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_xml = root / "source.xml"
            target_xml = root / "target.xml"
            source_xml.write_text(XML, encoding="utf-8")
            target_xml.write_text(TARGET_XML, encoding="utf-8")
            catalog = load_action_catalog(source_xml)
            target_catalog = load_action_catalog(target_xml)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("TransformIntoTutel")
            runtime.tick()
            events_after_first_tick = runtime.pop_transform_events()
            runtime.tick()
            events_after_second_tick = runtime.pop_transform_events()
            runtime.apply_transform(target_catalog, None, events_after_second_tick[0].behavior)

        self.assertEqual(events_after_first_tick, [])
        self.assertEqual(events_after_second_tick, [TransformEvent("Tuteling", "StandUp")])
        self.assertIs(runtime.catalog, target_catalog)
        self.assertEqual(runtime.action_name, "Stand")
        self.assertEqual(runtime.frame.image, "target-stand.png")

    def test_runtime_self_destruct_action_emits_event_after_animation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("SelfDestruct")
            runtime.tick()
            events_after_first_tick = runtime.pop_self_destruct_events()
            runtime.tick()
            events_after_second_tick = runtime.pop_self_destruct_events()
            runtime.tick()
            events_after_third_tick = runtime.pop_self_destruct_events()

        self.assertEqual(events_after_first_tick, [])
        self.assertEqual(events_after_second_tick, [SelfDestructEvent("SelfDestruct")])
        self.assertEqual(events_after_third_tick, [])

    def test_runtime_breed_action_emits_child_spawn_event_after_animation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.look_right = True
            runtime.start_action("BreedChild")
            runtime.tick()
            events_after_first_tick = runtime.pop_breed_events()
            runtime.tick()
            events_after_second_tick = runtime.pop_breed_events()
            runtime.tick()
            events_after_third_tick = runtime.pop_breed_events()

        self.assertEqual(events_after_first_tick, [])
        self.assertEqual(
            events_after_second_tick,
            [
                BreedEvent(
                    image_set="Tuteling Cursor",
                    behavior="ThrowIEFromLeft",
                    anchor_x=144,
                    anchor_y=252,
                    look_right=True,
                    transient=True,
                )
            ],
        )
        self.assertEqual(events_after_third_tick, [])

    def test_runtime_breed_move_emits_child_spawn_events_during_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            current_image_set = catalog.image_set_dir.name

            runtime.start_action("BreedRun", look_right=True, target_x=164)
            runtime.tick()
            events_after_first_tick = runtime.pop_breed_events()
            runtime.tick()
            events_after_second_tick = runtime.pop_breed_events()

        self.assertEqual(runtime.anchor_x, 164)
        self.assertEqual(runtime.action_name, "Stand")
        self.assertEqual(
            events_after_first_tick,
            [
                BreedEvent(
                    image_set=current_image_set,
                    behavior="RunChild",
                    anchor_x=146,
                    anchor_y=252,
                    look_right=True,
                    transient=False,
                )
            ],
        )
        self.assertEqual(
            events_after_second_tick,
            [
                BreedEvent(
                    image_set=current_image_set,
                    behavior="RunChild",
                    anchor_x=148,
                    anchor_y=252,
                    look_right=True,
                    transient=False,
                )
            ],
        )

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_real_neuron_split_continues_through_nested_divided_sequence(self) -> None:
        actions_xml = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"
        catalog = load_action_catalog(actions_xml)
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1400, 900), start_x=700, start_y=900))

        runtime.start_action("SplitIntoTwo")
        events = []
        for _ in range(41):
            runtime.tick()
            events.extend(runtime.pop_breed_events())

        self.assertEqual(len(events), 1)
        self.assertEqual(runtime.action_name, "Falling")
        self.assertTrue(runtime.frame.image)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_real_neuron_leaves_screen_ceiling_after_short_dwell(self) -> None:
        conf = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf"
        catalog = load_action_catalog(conf / "actions.xml")
        behaviors = load_behavior_catalog(conf / "behaviors.xml")
        runtime = PetRuntime(
            catalog,
            RuntimeConfig(work_area=Rect(0, 35, 1400, 865), start_x=700, start_y=35),
            behavior_catalog=behaviors,
        )

        with patch("src.runtime.random.random", return_value=0.5):
            runtime.start_action("HoldOntoCeiling")
            for _ in range(300):
                runtime.tick()

        self.assertGreater(runtime.anchor_y, runtime.config.work_area.top)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_real_neuron_long_sit_finishes_within_six_seconds(self) -> None:
        actions_xml = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"
        catalog = load_action_catalog(actions_xml)
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1400, 900), start_x=700, start_y=900))

        with patch("src.runtime.random.random", return_value=0.5):
            runtime.start_action("SitDown")
            for _ in range(151):
                runtime.tick()

        self.assertEqual(runtime.action_name, "Stand")

    def test_wall_grab_without_explicit_duration_eventually_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=0, start_y=120))

            runtime.start_action("GrabWall", auto_edge_climb=False)
            for _ in range(151):
                runtime.tick()

        self.assertNotEqual(runtime.action_name, "GrabWall")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_real_neuron_next_behavior_avoids_immediate_repeat_when_alternative_exists(self) -> None:
        conf = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf"
        runtime = PetRuntime(
            load_action_catalog(conf / "actions.xml"),
            RuntimeConfig(work_area=Rect(0, 0, 1400, 900), start_x=700, start_y=900),
            behavior_catalog=load_behavior_catalog(conf / "behaviors.xml"),
        )

        with patch("src.runtime.random.choices", side_effect=lambda items, **_kwargs: [items[0]]):
            next_behavior = runtime._choose_next_behavior("SitAndFaceMouse")

        self.assertEqual(next_behavior[0], "SitWhileDanglingLegs")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_real_neuron_direct_wink_animation_finishes_without_explicit_duration(self) -> None:
        actions_xml = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"
        catalog = load_action_catalog(actions_xml)
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1400, 900), start_x=700, start_y=900))

        runtime.start_action("Wink")
        for _ in range(30):
            runtime.tick()

        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_breed_jump_emits_child_spawn_event_during_jump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            current_image_set = catalog.image_set_dir.name

            runtime.start_action("BreedLeap", target_x=184, target_y=260)
            runtime.tick()
            events_after_first_tick = runtime.pop_breed_events()

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (184, 260))
        self.assertEqual(runtime.action_name, "Stand")
        self.assertEqual(
            events_after_first_tick,
            [
                BreedEvent(
                    image_set=current_image_set,
                    behavior="LeapChild",
                    anchor_x=168,
                    anchor_y=252,
                    look_right=True,
                    transient=False,
                )
            ],
        )

    def test_runtime_embedded_scan_move_on_floor_moves_toward_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("RunAffordance", target_x=200)
            runtime.tick()

        self.assertEqual(runtime.action_name, "RunAffordance")
        self.assertEqual(runtime.target_x, 200)
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.anchor_x, 168)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_scan_move_uses_target_anchor_animation_condition(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=400, start_y=1080))

        runtime.start_action("RunToThrow", target_x=900)
        runtime.tick()

        self.assertEqual(runtime.action_name, "RunToThrow")
        self.assertEqual(runtime.frame.image, "sprint1.png")
        self.assertEqual(runtime.anchor_x, 420)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_floor_run_retargets_when_random_target_is_current_anchor(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=960, start_y=1080))

        with patch("src.runtime.random.random", return_value=0.5):
            runtime.start_action("RunAlongWorkAreaFloor")
        runtime.tick()

        self.assertEqual(runtime.action_name, "Run")
        self.assertIsNotNone(runtime.target_x)
        self.assertGreaterEqual(abs(runtime.target_x - 960), 96)
        self.assertNotEqual(runtime.anchor_x, 960)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_chase_mouse_keeps_short_random_dash_target(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=1000, start_y=1080))

        runtime.update_cursor_pos(1200, 1080)
        with patch("src.runtime.random.random", return_value=0.5):
            runtime.start_action("ChaseMouse")

        self.assertEqual(runtime.action_name, "Dash")
        self.assertEqual(runtime.target_x, 1050)
        self.assertTrue(runtime.look_right)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_real_chase_mouse_stays_near_a_stationary_cursor(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Eviling/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(3200, 35, 2560, 1565), start_x=3600, start_y=1600))
        runtime.update_cursor_pos(4500, 700)
        positions = []
        with patch("src.runtime.random.random", return_value=0.5):
            for _ in range(1000):
                if runtime.ready_for_idle:
                    runtime.start_action("ChaseMouse")
                runtime.tick()
                positions.append(runtime.anchor_x)

        self.assertLessEqual(abs(runtime.anchor_x - 4500), 32)
        self.assertLessEqual(max(positions[-200:]) - min(positions[-200:]), 2)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_follow_cursor_stops_and_retargets_each_real_pet(self) -> None:
        image_sets = Path("refs/The-Neuroling-Collection/img")
        for name in ("Broken Neuron", "Evil Neuroling", "Eviling", "Neuroling", "Neuron", "Tuteling", "Vedaling", "Weuron"):
            with self.subTest(name=name):
                catalog = load_action_catalog(image_sets / name / "conf/actions.xml")
                runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(3200, 35, 2560, 1565), start_x=4000, start_y=1600))
                runtime.update_cursor_pos(4400, 700)
                with patch("src.runtime.random.random", return_value=0.5):
                    for _ in range(350):
                        runtime.follow_cursor()
                        runtime.tick()
                    stopped_x = runtime.anchor_x
                    self.assertLessEqual(abs(stopped_x - 4400), 32)
                    for _ in range(50):
                        runtime.follow_cursor()
                        runtime.tick()
                        self.assertEqual(runtime.anchor_x, stopped_x)
                    runtime.update_cursor_pos(4800, 800)
                    runtime.follow_cursor()
                    runtime.tick()
                    self.assertGreater(runtime.anchor_x, stopped_x)
                    before_turn = runtime.anchor_x
                    runtime.update_cursor_pos(3800, 500)
                    for _ in range(10):
                        runtime.follow_cursor()
                        runtime.tick()
                    self.assertLess(runtime.anchor_x, before_turn)
                    self.assertFalse(runtime.pop_self_destruct_events())

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_follow_cursor_leaves_drag_and_window_interactions_running(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 1920, 1080), start_x=400, start_y=1080))
        runtime.update_cursor_pos(900, 600)
        self.assertTrue(runtime.pointer_down(400, 1000, image_width=128, image_height=128))
        runtime.follow_cursor()
        self.assertTrue(runtime.pointer_active)
        runtime.pointer_up(400, 1080)
        runtime.update_active_window_rect(Rect(200, 500, 400, 300))
        self.assertTrue(runtime.start_window_interaction(Rect(200, 500, 400, 300), throw=True))
        action = runtime.action_name
        runtime.follow_cursor()
        self.assertEqual(runtime.action_name, action)
        self.assertTrue(runtime.window_action_active)

    def test_runtime_scan_move_targets_affordance_pet_and_emits_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(INTERACTION_XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            world = PetWorld()
            runner = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            target = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=184, start_y=260))
            world.register(runner)
            world.register(target)

            target.start_action("SitAffordance")
            runner.start_action("RunAffordance")
            target_x_after_start = runner.target_x
            for _ in range(3):
                runner.tick()
            events = runner.pop_interaction_events()

        self.assertEqual(target_x_after_start, 184)
        self.assertEqual(runner.action_name, "StandBlush")
        self.assertEqual(runner.anchor_x, 184)
        self.assertEqual(
            events,
            [
                InteractionEvent(
                    target=target,
                    target_behavior="Stand",
                    target_look=True,
                    source_look_right=True,
                )
            ],
        )

    def test_runtime_scan_jump_targets_affordance_pet_and_emits_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(INTERACTION_XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            world = PetWorld()
            jumper = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            target = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=184, start_y=260))
            world.register(jumper)
            world.register(target)

            target.start_action("SitAffordance")
            jumper.start_action("LeapAffordance")
            target_x_after_start = jumper.target_x
            target_y_after_start = jumper.target_y
            jumper.tick()
            events = jumper.pop_interaction_events()

        self.assertEqual((target_x_after_start, target_y_after_start), (184, 260))
        self.assertEqual((jumper.anchor_x, jumper.anchor_y), (184, 260))
        self.assertEqual(jumper.action_name, "StandBlush")
        self.assertEqual(
            events,
            [
                InteractionEvent(
                    target=target,
                    target_behavior="Stand",
                    target_look=True,
                    source_look_right=True,
                )
            ],
        )

    def test_runtime_scan_interact_targets_affordance_pet_after_animation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(INTERACTION_XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            world = PetWorld()
            source = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            target = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=184, start_y=260))
            world.register(source)
            world.register(target)

            target.start_action("SitAffordance")
            source.start_action("WaveAffordance")
            source.tick()
            target_x_after_first_tick = source.target_x
            look_right_after_first_tick = source.look_right
            action_after_first_tick = source.action_name
            events_after_first_tick = source.pop_interaction_events()
            source.tick()
            events_after_second_tick = source.pop_interaction_events()

        self.assertEqual(action_after_first_tick, "WaveAffordance")
        self.assertEqual(target_x_after_first_tick, 184)
        self.assertTrue(look_right_after_first_tick)
        self.assertEqual(events_after_first_tick, [])
        self.assertEqual(source.action_name, "StandBlush")
        self.assertEqual(
            events_after_second_tick,
            [
                InteractionEvent(
                    target=target,
                    target_behavior="Stand",
                    target_look=True,
                    source_look_right=True,
                )
            ],
        )

    def test_runtime_scan_interact_plays_turn_animation_before_interacting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(INTERACTION_XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            world = PetWorld()
            source = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            target = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=184, start_y=260))
            world.register(source)
            world.register(target)

            target.start_action("SitAffordance")
            source.look_right = False
            source.start_action("TurnWaveAffordance")
            source.tick()
            frame_after_first_tick = source.frame.image
            action_after_first_tick = source.action_name
            events_after_first_tick = source.pop_interaction_events()
            source.tick()
            events_after_second_tick = source.pop_interaction_events()
            action_after_second_tick = source.action_name
            source.tick()
            events_after_third_tick = source.pop_interaction_events()

        self.assertEqual(frame_after_first_tick, "scan-interact-turn.png")
        self.assertEqual(action_after_first_tick, "TurnWaveAffordance")
        self.assertEqual(events_after_first_tick, [])
        self.assertEqual(action_after_second_tick, "TurnWaveAffordance")
        self.assertEqual(events_after_second_tick, [])
        self.assertEqual(source.action_name, "StandBlush")
        self.assertEqual(
            events_after_third_tick,
            [
                InteractionEvent(
                    target=target,
                    target_behavior="Stand",
                    target_look=False,
                    source_look_right=True,
                )
            ],
        )

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_interact_action_finishes_after_animation_duration(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        world = PetWorld()
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 640, 260), start_x=160, start_y=260))
        target = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 640, 260), start_x=160, start_y=260))
        world.register(runtime)
        world.register(target)

        runtime.start_action("HugAction")
        for _ in range(103):
            runtime.tick()

        self.assertEqual(runtime.action_name, "Stand")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_runtime_real_interact_action_stops_when_anchor_no_longer_overlaps_target(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))
        world = PetWorld()
        source = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 640, 260), start_x=160, start_y=260))
        target = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 640, 260), start_x=160, start_y=260))
        world.register(source)
        world.register(target)

        source.start_action("HugAction")
        source.tick()
        target.anchor_x = 320
        source.tick()

        self.assertEqual(source.action_name, "Stand")

    def test_runtime_embedded_scan_move_without_target_uses_finite_floor_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.start_action("RunAffordance")
            for _ in range(8):
                runtime.tick()

        self.assertEqual(runtime.anchor_x, 96)
        self.assertEqual(runtime.action_name, "Stand")

    def test_runtime_scan_move_with_world_stops_when_affordance_target_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(INTERACTION_XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            world = PetWorld()
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))
            world.register(runtime)

            runtime.start_action("RunAffordance")
            runtime.tick()

        self.assertEqual(runtime.action_name, "Stand")
        self.assertIsNone(runtime.target_x)
        self.assertEqual(runtime.anchor_x, 160)

    def test_runtime_action_reference_params_are_available_to_target_expressions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            runtime.update_cursor_pos(220, 260)
            runtime.start_action("DashTowardMouseWithGap")
            runtime.tick()

        self.assertEqual(runtime.action_name, "Run")
        self.assertEqual(runtime.target_x, 200)
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.anchor_x, 166)

    def test_runtime_border_conditions_are_not_corrupted_by_shorter_variable_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=0, start_y=120))

            runtime.start_action("EscapeLeftWallThenFall")

        self.assertEqual(runtime.action_name, "Falling")
        self.assertEqual(runtime.anchor_x, 1)

    def test_runtime_idle_actions_include_floor_animations_beyond_walking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            candidates = runtime.available_idle_actions()

        self.assertIn("SitDown", candidates)
        self.assertIn("LieDown", candidates)
        self.assertIn("HeartHeartHeart", candidates)
        self.assertIn("WalkAlongWorkAreaFloor", candidates)
        self.assertGreater(len(candidates), 3)

    def test_runtime_idle_scheduler_can_start_non_walk_sequence(self) -> None:
        class PickLieDown:
            def choice(self, items):
                if "LieDown" not in items:
                    raise AssertionError(f"LieDown not in idle candidates: {items}")
                return "LieDown"

            def randint(self, left, _right):
                return left

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260))

            started = runtime.start_idle_action(rng=PickLieDown())

        self.assertTrue(started)
        self.assertEqual(runtime.action_name, "Sprawl")

    def test_runtime_idle_scheduler_prefers_environment_matching_behaviors_when_catalog_is_available(self) -> None:
        class PickWeightedLieDown:
            weights_by_name = {}

            def choices(self, names, *, weights, k):
                self.weights_by_name = dict(zip(names, weights))
                return ["LieDown"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )
            rng = PickWeightedLieDown()

            candidates = runtime.available_idle_actions()
            started = runtime.start_idle_action(rng=rng)

        self.assertEqual(candidates, ["SitDown", "LieDown"])
        self.assertEqual(rng.weights_by_name, {"SitDown": 25, "LieDown": 75})
        self.assertTrue(started)
        self.assertEqual(runtime.action_name, "Sprawl")

    def test_runtime_behavior_catalog_includes_unconditional_behaviors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(RICH_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            candidates = runtime.available_idle_actions()

        self.assertIn("SitAndFaceMouse", candidates)

    def test_runtime_behavior_action_mapping_starts_action_while_tracking_behavior_name(self) -> None:
        class PickPretendLie:
            def choices(self, names, *, weights, k):
                if "PretendLie" not in names:
                    raise AssertionError(f"PretendLie not in idle candidates: {names}")
                return ["PretendLie"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(ACTION_ALIAS_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            candidates = runtime.available_idle_actions()
            started = runtime.start_idle_action(rng=PickPretendLie())

        self.assertEqual(candidates, ["PretendLie", "PretendSit"])
        self.assertTrue(started)
        self.assertEqual(runtime.action_name, "Sprawl")
        self.assertEqual(runtime._behavior_name, "PretendLie")

    def test_runtime_behavior_catalog_evaluates_active_window_composite_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(RICH_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 420, 260), start_x=120, start_y=191),
                behavior_catalog=behavior_catalog,
            )

            runtime.update_active_window_rect(Rect(200, 100, 160, 120))
            candidates = runtime.available_idle_actions()

        self.assertIn("WalkAlongWorkAreaFloor", candidates)

    def test_runtime_behavior_catalog_evaluates_total_count_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(TOTAL_COUNT_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )
            world = PetWorld()

            candidates_without_world = runtime.available_idle_actions()
            world.register(runtime)
            world.register(PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=180, start_y=260)))
            candidates_with_two_pets = runtime.available_idle_actions()

        self.assertIn("BreedChild", candidates_without_world)
        self.assertNotIn("BreedChild", candidates_with_two_pets)

    def test_runtime_finished_behavior_uses_non_additive_next_behavior_list(self) -> None:
        class PickLieDown:
            def choices(self, names, *, weights, k):
                if "LieDown" not in names:
                    raise AssertionError(f"LieDown not in idle candidates: {names}")
                return ["LieDown"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(NEXT_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            self.assertTrue(runtime.start_idle_action(rng=PickLieDown()))
            for _ in range(4):
                runtime.tick()

        self.assertEqual(runtime.action_name, "Sit")

    def test_runtime_next_behavior_reference_action_mapping_starts_mapped_action(self) -> None:
        class PickPretendSit:
            def choices(self, names, *, weights, k):
                if "PretendSit" not in names:
                    raise AssertionError(f"PretendSit not in idle candidates: {names}")
                return ["PretendSit"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(ACTION_ALIAS_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            self.assertTrue(runtime.start_idle_action(rng=PickPretendSit()))
            for _ in range(4):
                runtime.tick()

        self.assertEqual(runtime.action_name, "Sprawl")
        self.assertEqual(runtime._behavior_name, "PretendLieNext")

    def test_runtime_additive_next_behaviors_extend_global_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(NEXT_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            weighted = runtime._weighted_behavior_idle_actions(previous_behavior="SitDown")

        self.assertEqual(weighted, [("SitDown", 25), ("LieDown", 75), ("LieDown", 100)])

    def test_runtime_next_behavior_conditions_are_evaluated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(NEXT_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            weighted = runtime._weighted_behavior_idle_actions(previous_behavior="LieDown")

        self.assertEqual(weighted, [("SitDown", 7)])

    def test_runtime_next_behavior_runs_after_sequence_ends_with_instant_reference(self) -> None:
        class PickSitAndFaceMouse:
            def choices(self, names, *, weights, k):
                if "SitAndFaceMouse" not in names:
                    raise AssertionError(f"SitAndFaceMouse not in idle candidates: {names}")
                return ["SitAndFaceMouse"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions_xml = root / "actions.xml"
            behaviors_xml = root / "behaviors.xml"
            actions_xml.write_text(XML, encoding="utf-8")
            behaviors_xml.write_text(INSTANT_END_NEXT_BEHAVIORS_XML, encoding="utf-8")
            catalog = load_action_catalog(actions_xml)
            behavior_catalog = load_behavior_catalog(behaviors_xml)
            runtime = PetRuntime(
                catalog,
                RuntimeConfig(work_area=Rect(0, 0, 320, 260), start_x=160, start_y=260),
                behavior_catalog=behavior_catalog,
            )

            self.assertTrue(runtime.start_idle_action(rng=PickSitAndFaceMouse()))
            for _ in range(2):
                runtime.tick()

        self.assertEqual(runtime.action_name, "Sprawl")

    def test_runtime_walk_with_ie_moves_active_window_with_mascot_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 420, 285), start_x=199, start_y=285))

            runtime.update_active_window_rect(Rect(200, 100, 160, 120))
            runtime.start_action("WalkWithIe", look_right=True, target_x=220)
            runtime.tick()

        self.assertEqual(runtime.action_name, "WalkWithIe")
        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (202, 285))
        self.assertEqual(runtime.active_window_rect, Rect(203, 100, 160, 120))
        self.assertEqual(runtime.desired_active_window_rect, Rect(203, 100, 160, 120))

    def test_runtime_walk_with_ie_falls_when_active_window_is_not_attached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 420, 285), start_x=199, start_y=285))

            runtime.update_active_window_rect(Rect(260, 100, 160, 120))
            runtime.start_action("WalkWithIe", look_right=True, target_x=220)
            runtime.tick()

        self.assertEqual(runtime.action_name, "Falling")
        self.assertEqual(runtime.active_window_rect, Rect(260, 100, 160, 120))
        self.assertIsNone(runtime.desired_active_window_rect)

    def test_runtime_fall_with_ie_falls_when_active_window_is_not_attached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 420, 285), start_x=199, start_y=285))

            runtime.update_active_window_rect(Rect(260, 100, 160, 120))
            runtime.start_action("FallWithIe", look_right=True)
            runtime.tick()

        self.assertEqual(runtime.action_name, "Falling")
        self.assertEqual(runtime.active_window_rect, Rect(260, 100, 160, 120))
        self.assertIsNone(runtime.desired_active_window_rect)

    def test_runtime_throw_ie_moves_active_window_on_ballistic_path_and_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml_path = root / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")
            catalog = load_action_catalog(xml_path)
            runtime = PetRuntime(catalog, RuntimeConfig(work_area=Rect(0, 0, 420, 285), start_x=220, start_y=285))

            runtime.update_active_window_rect(Rect(203, 100, 160, 120))
            runtime.start_action("ThrowIe", look_right=True)
            for _ in range(4):
                runtime.tick()

        self.assertEqual(runtime.active_window_rect, Rect(331, 62, 160, 120))
        self.assertEqual(runtime.desired_active_window_rect, Rect(331, 62, 160, 120))
        self.assertEqual(runtime.action_name, "Stand")


if __name__ == "__main__":
    unittest.main()
