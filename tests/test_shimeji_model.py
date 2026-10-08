import tempfile
import unittest
from pathlib import Path

from neuro_hypr_pet.shimeji_model import load_action_catalog, load_behavior_catalog


BEHAVIORS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Behavior Name="ChaseMouse" Frequency="10" Hidden="true">
      <NextBehaviorList Add="false">
        <BehaviorReference Name="SitAndFaceMouse" Frequency="30"/>
      </NextBehaviorList>
    </Behavior>
    <Condition Condition="#{mascot.environment.floor.isOn(mascot.anchor)}">
      <Behavior Name="SitDown" Frequency="200">
        <NextBehaviorList Add="true">
          <BehaviorReference Name="LieDown" Frequency="100" Condition="${ok}" Hidden="true"/>
        </NextBehaviorList>
      </Behavior>
    </Condition>
  </BehaviorList>
</Mascot>
"""


BEHAVIORS_WITH_ACTION_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <BehaviorList>
    <Behavior Name="CustomSit" Action="SitDown" Frequency="20">
      <NextBehaviorList Add="false">
        <BehaviorReference Name="CustomLie" Action="LieDown" Frequency="30"/>
      </NextBehaviorList>
    </Behavior>
  </BehaviorList>
</Mascot>
"""


ACTIONS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <ActionList>
    <Action Name="Look" Type="Embedded" Class="com.group_finity.mascot.action.Look"/>
    <Action Name="Offset" Type="Embedded" Class="com.group_finity.mascot.action.Offset"/>
    <Action Name="Walk" Type="Move" BorderType="Floor">
      <Animation>
        <Pose Image="/walk.png" ImageRight="/walk-r.png" ImageAnchor="64,128" Velocity="-2,0" Duration="4"
              Sound="knock.wav" Volume="1"/>
        <Hotspot Shape="Ellipse" Origin="38,15" Size="48,26" Behavior="StandBlush"/>
      </Animation>
    </Action>
    <Action Name="LegacyTurnWalk" Type="Embedded" Class="com.group_finity.mascot.action.MoveWithTurn" BorderType="Floor">
      <Animation>
        <Pose Image="/legacy-walk.png" ImageAnchor="64,128" Velocity="-2,0" Duration="4"/>
      </Animation>
      <Animation>
        <Pose Image="/legacy-turn.png" ImageAnchor="64,128" Velocity="0,0" Duration="4"/>
      </Animation>
    </Action>
    <Action Name="WalkAlongIECeiling" Type="Sequence" Loop="false">
      <ActionReference Name="Walk" TargetX="${mascot.environment.activeIE.left+64}"/>
      <ActionReference Name="Falling" InitialVX="-15" InitialVY="-20"/>
      <ActionReference Name="Stand" Duration="${100+Math.random()*100}"/>
    </Action>
    <Action Name="ClimbWall" Type="Move" BorderType="Wall">
      <Animation Condition="#{TargetY &lt; mascot.anchor.y}">
        <Pose Image="/climb-up.png" ImageAnchor="64,128" Velocity="0,-2" Duration="4"/>
      </Animation>
      <Animation Condition="#{TargetY &gt;= mascot.anchor.y}">
        <Pose Image="/climb-down.png" ImageAnchor="64,128" Velocity="0,2" Duration="4"/>
      </Animation>
    </Action>
    <Action Name="HoldInvisible" Type="Embedded" Class="com.group_finity.mascot.action.Interact" BorderType="Floor">
      <Animation>
        <Pose Velocity="0,0" Duration="93"/>
      </Animation>
    </Action>
    <Action Name="Fall" Type="Sequence" Loop="false">
      <ActionReference Name="Falling"/>
      <Action Type="Select">
        <Action Type="Sequence" Condition="${mascot.environment.floor.isOn(mascot.anchor)}">
          <ActionReference Name="Bouncing"/>
          <ActionReference Name="Stand" Duration="${100+Math.random()*100}"/>
        </Action>
        <ActionReference Name="GrabWall" Duration="100"/>
      </Action>
    </Action>
  </ActionList>
</Mascot>
"""


class ShimejiModelTest(unittest.TestCase):
    def test_load_action_catalog_keeps_sequence_action_references_without_pose_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        sequence = catalog.actions["WalkAlongIECeiling"]
        self.assertEqual(sequence.kind, "Sequence")
        self.assertFalse(sequence.loop)
        self.assertEqual(sequence.frames, ())
        self.assertEqual(len(sequence.references), 3)
        self.assertEqual(sequence.references[0].name, "Walk")
        self.assertEqual(sequence.references[0].params["TargetX"], "${mascot.environment.activeIE.left+64}")
        self.assertEqual(sequence.references[1].params["InitialVX"], "-15")
        self.assertEqual(sequence.references[1].params["InitialVY"], "-20")
        self.assertEqual(sequence.references[2].params["Duration"], "${100+Math.random()*100}")

    def test_load_action_catalog_attaches_animation_hotspots_to_pose_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        hotspot = catalog.actions["Walk"].frames[0].hotspots[0]
        self.assertEqual(hotspot.shape, "Ellipse")
        self.assertEqual((hotspot.x, hotspot.y, hotspot.width, hotspot.height), (38, 15, 48, 26))
        self.assertEqual(hotspot.behavior, "StandBlush")
        self.assertTrue(hotspot.contains(62, 28, image_width=128, look_right=False))
        self.assertTrue(hotspot.contains(66, 28, image_width=128, look_right=True))

    def test_load_action_catalog_preserves_image_right_for_directional_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        walk_frame = catalog.actions["Walk"].frames[0]
        self.assertEqual(walk_frame.image, "walk.png")
        self.assertEqual(walk_frame.image_right, "walk-r.png")
        self.assertEqual(walk_frame.sound, "knock.wav")
        self.assertEqual(walk_frame.sound_volume, 1.0)
        self.assertEqual(walk_frame.image_for_direction(look_right=False), "walk.png")
        self.assertEqual(walk_frame.image_for_direction(look_right=True), "walk-r.png")
        self.assertFalse(walk_frame.needs_horizontal_flip(look_right=True))

        climb_frame = catalog.actions["ClimbWall"].frames[0]
        self.assertEqual(climb_frame.image_for_direction(look_right=True), "climb-up.png")
        self.assertTrue(climb_frame.needs_horizontal_flip(look_right=True))

    def test_load_action_catalog_preserves_pose_without_image_as_transparent_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        hold = catalog.actions["HoldInvisible"]
        self.assertEqual(len(hold.frames), 1)
        self.assertEqual(hold.frames[0].image, "")
        self.assertEqual(hold.frames[0].duration, 93)

    def test_load_action_catalog_preserves_no_frame_instant_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        self.assertEqual(catalog.actions["Look"].params["Class"], "com.group_finity.mascot.action.Look")
        self.assertEqual(catalog.actions["Look"].frames, ())
        self.assertEqual(catalog.actions["Offset"].params["Class"], "com.group_finity.mascot.action.Offset")
        self.assertEqual(catalog.actions["Offset"].references, ())

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_load_real_neuroling_hold_only_actions(self) -> None:
        catalog = load_action_catalog(Path("refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"))

        hugged = catalog.actions["HuggedAction"]

        self.assertEqual(len(hugged.frames), 1)
        self.assertEqual(hugged.frames[0].image, "")
        self.assertEqual(hugged.frames[0].duration, 93)

    def test_load_action_catalog_marks_legacy_move_with_turn_last_animation_as_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        legacy = catalog.actions["LegacyTurnWalk"]
        self.assertFalse(legacy.animations[0].is_turn)
        self.assertTrue(legacy.animations[1].is_turn)

    def test_load_action_catalog_preserves_animation_conditions_as_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        climb = catalog.actions["ClimbWall"]
        self.assertEqual(len(climb.animations), 2)
        self.assertEqual(climb.animations[0].condition, "#{TargetY < mascot.anchor.y}")
        self.assertEqual(climb.animations[0].frames[0].image, "climb-up.png")
        self.assertEqual(climb.animations[1].condition, "#{TargetY >= mascot.anchor.y}")
        self.assertEqual(climb.animations[1].frames[0].image, "climb-down.png")
        self.assertEqual([frame.image for frame in climb.frames], ["climb-up.png", "climb-down.png"])

    def test_load_action_catalog_preserves_inline_select_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(ACTIONS_XML, encoding="utf-8")

            catalog = load_action_catalog(xml_path)

        fall = catalog.actions["Fall"]
        self.assertEqual(len(fall.references), 2)
        select = fall.references[1]
        self.assertEqual(select.kind, "Select")
        self.assertEqual(len(select.references), 2)
        floor_sequence = select.references[0]
        self.assertEqual(floor_sequence.kind, "Sequence")
        self.assertEqual(floor_sequence.params["Condition"], "${mascot.environment.floor.isOn(mascot.anchor)}")
        self.assertEqual(floor_sequence.references[0].name, "Bouncing")
        self.assertEqual(select.references[1].name, "GrabWall")

    def test_load_behavior_catalog_reads_frequency_hidden_and_next_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "behaviors.xml"
            xml_path.write_text(BEHAVIORS_XML, encoding="utf-8")

            catalog = load_behavior_catalog(xml_path)

        chase = catalog.behaviors["ChaseMouse"]
        self.assertEqual(chase.frequency, 10)
        self.assertTrue(chase.hidden)
        self.assertIsNone(chase.condition)
        self.assertFalse(chase.next_add)
        self.assertEqual(len(chase.next_behaviors), 1)
        self.assertEqual(chase.next_behaviors[0].name, "SitAndFaceMouse")
        self.assertEqual(chase.next_behaviors[0].frequency, 30)

    def test_load_behavior_catalog_preserves_behavior_action_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "behaviors.xml"
            xml_path.write_text(BEHAVIORS_WITH_ACTION_XML, encoding="utf-8")

            catalog = load_behavior_catalog(xml_path)

        custom = catalog.behaviors["CustomSit"]
        self.assertEqual(custom.name, "CustomSit")
        self.assertEqual(custom.action_name, "SitDown")
        self.assertEqual(custom.next_behaviors[0].name, "CustomLie")
        self.assertEqual(custom.next_behaviors[0].action_name, "LieDown")

    def test_load_behavior_catalog_inherits_condition_group_for_nested_behaviors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "behaviors.xml"
            xml_path.write_text(BEHAVIORS_XML, encoding="utf-8")

            catalog = load_behavior_catalog(xml_path)

        sit = catalog.behaviors["SitDown"]
        self.assertEqual(sit.frequency, 200)
        self.assertEqual(sit.condition, "#{mascot.environment.floor.isOn(mascot.anchor)}")
        self.assertTrue(sit.next_add)
        self.assertEqual(sit.next_behaviors[0].name, "LieDown")
        self.assertEqual(sit.next_behaviors[0].frequency, 100)
        self.assertEqual(sit.next_behaviors[0].condition, "${ok}")
        self.assertTrue(sit.next_behaviors[0].hidden)


if __name__ == "__main__":
    unittest.main()
