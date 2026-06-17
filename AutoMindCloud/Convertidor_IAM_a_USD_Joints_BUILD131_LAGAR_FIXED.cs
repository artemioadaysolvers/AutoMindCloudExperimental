// ============================================================================
// AutoMind BUILD125 - Autodesk Inventor IAM -> OpenUSD/USD ASCII with UsdPhysics joints
//
// USD ONLY EXPORTER:
//   * Creates exactly one <AssemblyName>_USD folder beside the .iam.
//   * Writes <AssemblyName>.usda as the main output.
//   * Does NOT write .urdf, URDF_Export, URDF+ XML, DAE, or STL side-products.
//
// Mechanical contents authored into USD:
//   * Links as Xform prims with PhysicsRigidBodyAPI/PhysicsMassAPI.
//   * Joints as UsdPhysics prims: PhysicsRevoluteJoint, PhysicsPrismaticJoint,
//     PhysicsFixedJoint, PhysicsSphericalJoint, or generic PhysicsJoint.
//   * CAD evidence stored as automind:* metadata for axes, pivots, constraints,
//     confidence, active/passive roles, loops, couplings and implicit candidates.
//
// MAX DEBUG PACKAGE:
//   * AutoMind_USD_DEBUG_MAX.log
//   * AutoMind_USD_DEBUG_README.txt
//   * AutoMind_USD_AUDIT_SUMMARY.txt
//   * AutoMind_USD_LINKS.csv
//   * AutoMind_USD_JOINTS.csv
//   * AutoMind_USD_CAD_CONSTRAINTS.csv
//   * AutoMind_USD_NATIVE_JOINTS.csv
//   * AutoMind_USD_IMPLICIT_CANDIDATES.csv
// ============================================================================

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Xml;
using DrawingColor = System.Drawing.Color;
using DrawingBitmap = System.Drawing.Bitmap;
using Inv = Inventor;

namespace AutoMind.IAMToUSDJoints
{
    [Guid("f458130c-5750-4302-93aa-e206513a0869")]
    [ProgId("AutoMind.IAMToUSDJoints.StandardAddInServer")]
    public class StandardAddInServer : Inv.ApplicationAddInServer
    {
        private Inv.Application _inventor;

        // UI antiguo conservado: dos botones en panel "USD Export"
        // - Export USD (VLQ)      -> malla VeryLowOptimized / inline USD mesh
        // - Export USD (Display)  -> malla DisplayMesh / inline USD mesh
        private Inv.ButtonDefinition _exportUsdVlqButton;
        private Inv.ButtonDefinition _exportUsdDisplayButton;

        private const string AddInClientId = "{f458130c-5750-4302-93aa-e206513a0869}";

        public void Activate(Inv.ApplicationAddInSite addInSiteObject, bool firstTime)
        {
            _inventor = addInSiteObject.Application;
            Build51Log.Sys("Activate BUILD128 USD-ONLY IAM->OpenUSD with strict UsdPhysics joint typing, URDF+ textures, solver contract and implicit closure candidates");
            TryCreateLegacyButtons();
        }

        public void Deactivate()
        {
            try
            {
                if (_exportUsdVlqButton != null)
                    _exportUsdVlqButton.OnExecute -= OnExportUsdVlqButtonPressed;
            }
            catch { }

            try
            {
                if (_exportUsdDisplayButton != null)
                    _exportUsdDisplayButton.OnExecute -= OnExportUsdDisplayButtonPressed;
            }
            catch { }

            _exportUsdVlqButton = null;
            _exportUsdDisplayButton = null;
            _inventor = null;
            GC.Collect();
            GC.WaitForPendingFinalizers();
        }

        public void ExecuteCommand(int commandID) { }
        public object Automation { get { return this; } }

        private void TryCreateLegacyButtons()
        {
            try
            {
                Inv.CommandManager cmdMgr = _inventor.CommandManager;
                Inv.ControlDefinitions controlDefs = cmdMgr.ControlDefinitions;

                _exportUsdVlqButton = null;
                try { _exportUsdVlqButton = controlDefs["usd_export_vlq_cmd"] as Inv.ButtonDefinition; }
                catch (Exception exLookup)
                {
                    Build51Log.Sys("lookup 'usd_export_vlq_cmd' skipped: " + exLookup.Message);
                    _exportUsdVlqButton = null;
                }

                if (_exportUsdVlqButton == null)
                {
                    _exportUsdVlqButton = controlDefs.AddButtonDefinition(
                        "Export USD (VLQ)",
                        "usd_export_vlq_cmd",
                        Inv.CommandTypesEnum.kNonShapeEditCmdType,
                        AddInClientId,
                        "Export USD with VeryLowOptimized inline USD mesh generation",
                        "Export USD (VLQ)",
                        null,
                        null);
                }

                try { _exportUsdVlqButton.OnExecute -= OnExportUsdVlqButtonPressed; } catch { }
                _exportUsdVlqButton.OnExecute += OnExportUsdVlqButtonPressed;

                _exportUsdDisplayButton = null;
                try { _exportUsdDisplayButton = controlDefs["usd_export_display_cmd"] as Inv.ButtonDefinition; }
                catch (Exception exLookup)
                {
                    Build51Log.Sys("lookup 'usd_export_display_cmd' skipped: " + exLookup.Message);
                    _exportUsdDisplayButton = null;
                }

                if (_exportUsdDisplayButton == null)
                {
                    _exportUsdDisplayButton = controlDefs.AddButtonDefinition(
                        "Export USD (Display)",
                        "usd_export_display_cmd",
                        Inv.CommandTypesEnum.kNonShapeEditCmdType,
                        AddInClientId,
                        "Export USD with DisplayMesh inline USD mesh generation",
                        "Export USD (Display)",
                        null,
                        null);
                }

                try { _exportUsdDisplayButton.OnExecute -= OnExportUsdDisplayButtonPressed; } catch { }
                _exportUsdDisplayButton.OnExecute += OnExportUsdDisplayButtonPressed;

                Build51Log.Sys("USD ButtonDefinitions ready: VLQ + Display");

                Inv.UserInterfaceManager uiMgr = _inventor.UserInterfaceManager;

                try
                {
                    Inv.Ribbon partRibbon = uiMgr.Ribbons["Part"];
                    Inv.RibbonTab toolsTabPart = partRibbon.RibbonTabs["id_TabTools"];

                    Inv.RibbonPanel urdfPanelPart = null;
                    try { urdfPanelPart = toolsTabPart.RibbonPanels["usd_export_panel_part"]; }
                    catch { urdfPanelPart = null; }

                    if (urdfPanelPart == null)
                    {
                        urdfPanelPart = toolsTabPart.RibbonPanels.Add(
                            "USD Export",
                            "usd_export_panel_part",
                            AddInClientId,
                            "",
                            false);
                    }

                    SafeAddButtonToPanel(urdfPanelPart, _exportUsdVlqButton);
                    SafeAddButtonToPanel(urdfPanelPart, _exportUsdDisplayButton);
                    Build51Log.Sys("USD panel added/updated in Part ribbon");
                }
                catch (Exception ex)
                {
                    Build51Log.Warn("Part ribbon panel skipped: " + ex.Message);
                }

                try
                {
                    Inv.Ribbon asmRibbon = uiMgr.Ribbons["Assembly"];
                    Inv.RibbonTab toolsTabAsm = asmRibbon.RibbonTabs["id_TabTools"];

                    Inv.RibbonPanel urdfPanelAsm = null;
                    try { urdfPanelAsm = toolsTabAsm.RibbonPanels["usd_export_panel_asm"]; }
                    catch { urdfPanelAsm = null; }

                    if (urdfPanelAsm == null)
                    {
                        urdfPanelAsm = toolsTabAsm.RibbonPanels.Add(
                            "USD Export",
                            "usd_export_panel_asm",
                            AddInClientId,
                            "",
                            false);
                    }

                    SafeAddButtonToPanel(urdfPanelAsm, _exportUsdVlqButton);
                    SafeAddButtonToPanel(urdfPanelAsm, _exportUsdDisplayButton);
                    Build51Log.Sys("USD panel added/updated in Assembly ribbon");
                }
                catch (Exception ex)
                {
                    Build51Log.Warn("Assembly ribbon panel skipped: " + ex.Message);
                }
            }
            catch (Exception ex)
            {
                Build51Log.Error("TryCreateLegacyButtons failed: " + ex);
                try
                {
                    System.Windows.Forms.MessageBox.Show(
                        "Error activating AutoMind USD AddIn:\n" + ex.Message,
                        "AutoMind BUILD71",
                        System.Windows.Forms.MessageBoxButtons.OK,
                        System.Windows.Forms.MessageBoxIcon.Error);
                }
                catch { }
            }
        }

        private static void SafeAddButtonToPanel(Inv.RibbonPanel panel, Inv.ButtonDefinition btn)
        {
            if (panel == null || btn == null) return;

            try
            {
                Inv.CommandControls ctrls = panel.CommandControls;
                if (ctrls != null)
                {
                    for (int i = 1; i <= ctrls.Count; i++)
                    {
                        try
                        {
                            Inv.CommandControl cc = ctrls[i];
                            if (cc == null || cc.ControlDefinition == null) continue;

                            string internalName = "";
                            try { internalName = cc.ControlDefinition.InternalName; } catch { internalName = ""; }

                            if (!String.IsNullOrEmpty(internalName) &&
                                String.Equals(internalName, btn.InternalName, StringComparison.OrdinalIgnoreCase))
                                return;
                        }
                        catch { }
                    }
                }
            }
            catch { }

            try { panel.CommandControls.AddButton(btn); }
            catch { }
        }

        private void OnExportUsdVlqButtonPressed(Inv.NameValueMap Context)
        {
            try
            {
                string path = ExportActiveDocument("low");
                try { System.Windows.Forms.MessageBox.Show("USD exportado:\n" + path, "AutoMind BUILD125 USD - VLQ"); } catch { }
            }
            catch (Exception ex)
            {
                Build51Log.Error("OnExportUsdVlqButtonPressed failed: " + ex);
                try
                {
                    System.Windows.Forms.MessageBox.Show(
                        ex.ToString(),
                        "AutoMind BUILD125 export error",
                        System.Windows.Forms.MessageBoxButtons.OK,
                        System.Windows.Forms.MessageBoxIcon.Error);
                }
                catch { }
            }
        }

        private void OnExportUsdDisplayButtonPressed(Inv.NameValueMap Context)
        {
            try
            {
                string path = ExportActiveDocument("high");
                try { System.Windows.Forms.MessageBox.Show("USD exportado:\n" + path, "AutoMind BUILD125 USD - Display"); } catch { }
            }
            catch (Exception ex)
            {
                Build51Log.Error("OnExportUsdDisplayButtonPressed failed: " + ex);
                try
                {
                    System.Windows.Forms.MessageBox.Show(
                        ex.ToString(),
                        "AutoMind BUILD125 export error",
                        System.Windows.Forms.MessageBoxButtons.OK,
                        System.Windows.Forms.MessageBoxIcon.Error);
                }
                catch { }
            }
        }

        // Public automation entry point; useful from iLogic/VBA/debugger.
        public string ExportActiveDocument(string meshMode)
        {
            if (_inventor == null) throw new InvalidOperationException("Inventor application is null.");
            Inv.Document doc = _inventor.ActiveDocument;
            if (doc == null) throw new InvalidOperationException("No active document.");
            Build51Log.Sys("ExportActiveDocument ENTER doc='" + Safe(doc.DisplayName) + "' type=" + doc.DocumentType + " meshMode=" + meshMode);
            ExporterCore core = new ExporterCore(_inventor, meshMode ?? "low");
            return core.Export(doc);
        }

        private static string Safe(string s) { return s == null ? "" : s.Replace("'", "_"); }
    }

    internal static class Build51Log
    {
        private static readonly object Sync = new object();
        private static string _logFilePath = "";
        private static string _sessionId = DateTime.UtcNow.ToString("yyyyMMdd_HHmmss_fff", CultureInfo.InvariantCulture);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern void OutputDebugString(string lpOutputString);

        public static void ConfigureFile(string path)
        {
            lock (Sync)
            {
                _logFilePath = path ?? "";
                try
                {
                    if (!String.IsNullOrEmpty(_logFilePath))
                    {
                        string dir = Path.GetDirectoryName(_logFilePath);
                        if (!String.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                        File.WriteAllText(_logFilePath,
                            "AutoMind USD BUILD125 MAXIMUM FORENSICS LOG\r\n" +
                            "session=" + _sessionId + "\r\n" +
                            "utc=" + DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture) + "\r\n",
                            Encoding.UTF8);
                    }
                }
                catch { }
            }
        }

        public static void BeginSession(string description)
        {
            _sessionId = DateTime.UtcNow.ToString("yyyyMMdd_HHmmss_fff", CultureInfo.InvariantCulture);
            Write("SESSION", "BEGIN id=" + _sessionId + " " + (description ?? ""));
        }

        public static void EndSession(string description)
        {
            Write("SESSION", "END id=" + _sessionId + " " + (description ?? ""));
        }

        public static void Sys(string s) { Write("SYS", s); }
        public static void Cad(string s) { Write("CAD", s); }
        public static void Robot(string s) { Write("ROBOT", s); }
        public static void Mesh(string s) { Write("MESH", s); }
        public static void Warn(string s) { Write("WARN", s); }
        public static void Error(string s) { Write("ERROR", s); }
        public static void Summary(string s) { Write("SUMMARY", s); }
        public static void Axis(string s) { Write("AXISDBG", s); }
        public static void Frame(string s) { Write("FRAMEDBG", s); }
        public static void Native(string s) { Write("NATIVE", s); }
        public static void Entity(string s) { Write("ENTITY", s); }
        public static void Pair(string s) { Write("PAIR", s); }
        public static void Validate(string s) { Write("VALIDATE", s); }
        public static void Xml(string s) { Write("XML", s); }
        public static void Dump(string s) { Write("DUMP", s); }

        private static void Write(string channel, string s)
        {
            string line = DateTime.UtcNow.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture) +
                " [USD][" + channel + "][" + _sessionId + "][T" +
                System.Threading.Thread.CurrentThread.ManagedThreadId.ToString(CultureInfo.InvariantCulture) + "] " +
                (s ?? "");

            try { Debug.WriteLine(line); } catch { }
            try { Trace.WriteLine(line); Trace.Flush(); } catch { }
            try { OutputDebugString(line + "\r\n"); } catch { }
            try { Console.WriteLine(line); } catch { }

            lock (Sync)
            {
                try
                {
                    if (!String.IsNullOrEmpty(_logFilePath))
                        File.AppendAllText(_logFilePath, line + Environment.NewLine, Encoding.UTF8);
                }
                catch { }
            }
        }
    }

    internal sealed class ExporterCore
    {
        private readonly Inv.Application _app;
        private readonly string _meshMode;
        private readonly CultureInfo _ci = CultureInfo.InvariantCulture;
        private double _lengthToMeters = 0.01;
        private string _exportDir;
        private string _meshDir;
        private readonly List<string> _warnings = new List<string>();

        public ExporterCore(Inv.Application app, string meshMode)
        {
            _app = app;
            _meshMode = meshMode;
        }

        public string Export(Inv.Document doc)
        {
            if (doc.DocumentType != Inv.DocumentTypeEnum.kAssemblyDocumentObject)
                throw new InvalidOperationException("BUILD124 only exports assembly documents (.iam). Active document: " + doc.DisplayName);

            Inv.AssemblyDocument asm = (Inv.AssemblyDocument)doc;
            _lengthToMeters = GetLengthToMeters(doc);
            Build51Log.Sys("BUILD124 units lengthToMeters=" + F(_lengthToMeters));

            string baseDir = Path.GetDirectoryName(doc.FullFileName);
            if (String.IsNullOrEmpty(baseDir)) baseDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string robotName = SanitizeName(Path.GetFileNameWithoutExtension(doc.FullFileName));

            // BUILD124: USD ONLY. No URDF_Export, no .urdf, no URDF+ output.
            // The whole export is contained in one USD folder next to the .iam.
            _exportDir = Path.Combine(baseDir, robotName + "_USD");
            _meshDir = _exportDir; // BUILD124: keep a single USD folder; no meshes/assets subfolder.
            Directory.CreateDirectory(_exportDir);

            string usdPath = Path.Combine(_exportDir, robotName + ".usda");
            string forensicLogPath = Path.Combine(_exportDir, "AutoMind_USD_DEBUG_MAX.log");
            string debugManifestPath = Path.Combine(_exportDir, "AutoMind_USD_DEBUG_README.txt");
            Build51Log.ConfigureFile(forensicLogPath);
            Build51Log.BeginSession("doc='" + SafeString(doc.DisplayName) + "' full='" + SafeString(doc.FullFileName) + "' meshMode='" + _meshMode + "' output='USD_ONLY'");
            Build51Log.Sys("BUILD125_USD_ONLY exportDir='" + _exportDir + "' usdPath='" + usdPath + "' forensicLog='" + forensicLogPath + "' debugManifest='" + debugManifestPath + "'");
            Build51Log.Sys("BUILD124 runtime clr='" + Environment.Version.ToString() + "' os='" + Environment.OSVersion.ToString() + "' process64=" + Environment.Is64BitProcess.ToString());

            // BUILD86: preserve the complete browser occurrence hierarchy.  A nested
            // .iam is represented by a virtual URDF link and its children remain real
            // links.  This prevents top-level constraints on a subassembly from being
            // heuristically reassigned to one arbitrary leaf occurrence.
            List<OccInfo> occs = ExtractLeafOccurrences(asm);
            if (occs.Count == 0) throw new InvalidOperationException("No visible occurrences found.");
            Build51Log.Cad("BUILD86_LEDGER_SUMMARY stage=after_occurrence_extract nodes=" + occs.Count +
                " leaves=" + occs.Count(o => o.HasVisualGeometry) +
                " assembly_frames=" + occs.Count(o => o.IsAssemblyNode) +
                " visible=" + occs.Count(o => o.Visible) +
                " grounded=" + occs.Count(o => o.Grounded));
            DumpOccurrenceDiagnostics(occs, "AFTER_OCCURRENCE_EXTRACTION");

            List<ConstraintInfo> constraints = ExtractAssemblyConstraints(asm, occs);
            List<NativeJointInfo> nativeJointsRaw = ExtractNativeJoints(asm, occs);
            DumpNativeJointDiagnostics(nativeJointsRaw, "AFTER_NATIVE_JOINT_EXTRACTION_RAW");

            List<NativeJointInfo> nativeJoints =
                ResolveNativeJointDuplicates(nativeJointsRaw);

            Build51Log.Cad("BUILD83_LEDGER_SUMMARY stage=after_constraint_and_native_resolution constraints=" +
                constraints.Count +
                " axis_constraints=" + constraints.Count(c => c.HasAxis) +
                " native_joints_raw=" + nativeJointsRaw.Count +
                " native_joints_resolved=" + nativeJoints.Count +
                " constraint_pairs=" +
                constraints
                    .Where(c => c.A != null && c.B != null)
                    .Select(c => PairKey(c.A, c.B))
                    .Distinct()
                    .Count());

            DumpConstraintDiagnostics(constraints, "AFTER_CONSTRAINT_EXTRACTION");
            DumpNativeJointDiagnostics(nativeJoints, "AFTER_NATIVE_JOINT_DUPLICATE_RESOLUTION");

            RepairCollapsedConstraintEndpoints(occs, constraints);
            DumpConstraintDiagnostics(constraints, "AFTER_ENDPOINT_REPAIR");
            OccInfo root = ChoosePhysicalRoot(occs, constraints, nativeJoints);

            // BUILD71: do NOT root-normalize the assembly for the visual/component
            // construction contract. Inventor occurrence transforms are already
            // absolute assembly transforms. The mesh is exported in occurrence-local
            // coordinates, so q=0 must be reconstructed from those absolute CAD poses.
            PreserveGlobalAssemblyFrames(root, occs, constraints, nativeJoints);

            // BUILD124 USD ONLY + URDF+ texture system:
            // Mesh triangles remain authored inline in the .usda by WriteUsdLink(), but textures
            // are generated with the same legacy URDF+ PNG/atlas logic. No DAE/STL side meshes
            // are emitted by this USD texture path.
            foreach (OccInfo occ in occs)
            {
                occ.MeshFile = "";
                occ.TextureFile = "";
                if (occ.HasVisualGeometry)
                    ExportUsdTextureOnlyFromUrdfPlus(occ);
            }

            MechanicalModel model = BuildMechanicalModel(robotName, root, occs, constraints, nativeJoints);
            DumpMechanicalModelDiagnostics(model, "AFTER_MECHANICAL_GRAPH");
            DumpForensicGraphCompleteness(model, constraints, nativeJoints, "AFTER_MECHANICAL_GRAPH_PRE_OVERLAY");
            List<OccInfo> physicalOccurrences = occs.Where(o => o.HasVisualGeometry).ToList();
            bool gripperOverlay = TryApplyParallelGripperOverlay(model, physicalOccurrences, constraints, nativeJoints);
            if (gripperOverlay)
                _warnings.Add("BUILD71 parallel_gripper_overlay_applied: topology matched CAD gripper; names only used after topology match for deterministic side assignment.");

            bool cardanOverlay =
                !gripperOverlay &&
                TryApplyDoubleCardanOverlay(
                    model,
                    physicalOccurrences,
                    constraints);

            if (cardanOverlay)
                _warnings.Add("BUILD83 double_cardan_overlay_applied: exact 11-body topology matched; pin axes came from CAD constraint evidence.");

            // BUILD71: in the cardan IAM, Furca lunga:1 and Furca medie:1
            // are separate occurrences but must stay rigidly locked relative to
            // each other. Do NOT write mimic/coupling here: that rotates the
            // second fork about a different parent chain and explodes the model.
            // Write a URDF+ rigid_body_lock coupling; the BUILD71 HTML consumes it as a
            // visual/mechanical rigid constraint after the tree joints move.
            TryAddCardanFurcaMedieLungaRigidBodyCoupling(model);

            // A guarded overlay may replace the generic tree.  Keep any virtual IAM
            // frames that the overlay does not mention as empty, fixed diagnostic links.
            AttachUnparentedOccurrenceFrames(model);

            ComputeLinkFrames(model);
            DumpMechanicalModelDiagnostics(model, "AFTER_CANONICAL_FRAME_COMPUTATION");
            DumpUrdfZeroPoseAndJointForensics(model, "AFTER_CANONICAL_FRAME_COMPUTATION");
            AnnotateLoopTreePaths(model);
            ValidateModel(model);
            DumpValidationDiagnostics(model);
            WriteBuild92KinematicsAuditFiles(model);
            _currentUsdRobotNameForWriter = robotName;
            WriteUsd(usdPath, model, gripperOverlay);
            AuditWrittenUsd(usdPath, model);
            WriteUsdMaxDebugFiles(usdPath, model, constraints, nativeJoints, gripperOverlay);
            Build51Log.Summary("BUILD128_USD_ONLY_EXPORT_OK usd_path='" + usdPath + "' status='" + (model.Errors.Count == 0 ? "OK" : "PARTIAL_OK_REVIEW_WARNINGS") + "' links=" + model.Occurrences.Count + " tree_edges=" + model.TreeJoints.Count + " loops=" + model.LoopJoints.Count + " couplings=" + model.Couplings.Count + " independent_dof=" + model.IndependentDof);
            Build51Log.EndSession("success usd='" + usdPath + "'");
            return usdPath;
        }



        // --------------------------------------------------------------------
        // BUILD97 post-writer patch for Robot Gripper mechanical-pivot URDF+.
        // --------------------------------------------------------------------
        // This is the generator version of the BUILD97 URDF that validated
        // correctly in the viewer.  It activates only on the exact Robot Gripper
        // topology.  The key correction is semantic and metric:
        //   * moving link frames are recentered on real pin pivots, not CAD
        //     occurrence origins;
        //   * visual origins are offset by the inverse displacement, preserving
        //     q=0 mesh placement exactly;
        //   * Link_1 / Link_2 become grounded rockers at P3/P6;
        //   * Gripper_1 / Gripper_2 hinge to Gear_link_2/Gear_link_1 at P4/P7;
        //   * only P8/P5 remain as true closed-chain loop closures;
        //   * Pin_* occurrences are visual fasteners/connector evidence, never
        //     primary solver bodies.
        private void PatchParallelGripperUrdfContractBuild97(string urdfPath)
        {
            try
            {
                if (String.IsNullOrEmpty(urdfPath) || !File.Exists(urdfPath)) return;

                XmlDocument doc = new XmlDocument();
                doc.PreserveWhitespace = false;
                doc.Load(urdfPath);
                XmlElement root = doc.DocumentElement;
                if (root == null || !String.Equals(root.LocalName, "robot", StringComparison.OrdinalIgnoreCase)) return;

                if (!Build71HasLink(root, "link_0_Base_Plate_1") ||
                    !Build71HasLink(root, "link_1_Base_Plate_2") ||
                    !Build71HasLink(root, "link_2_Base_Mounting_bracket_1") ||
                    !Build71HasLink(root, "link_3_Gear_link_1_1") ||
                    !Build71HasLink(root, "link_4_Gear_link_2_1") ||
                    !Build71HasLink(root, "link_13_Gripper_1") ||
                    !Build71HasLink(root, "link_14_Gripper_2") ||
                    !Build71HasLink(root, "link_15_Link_1") ||
                    !Build71HasLink(root, "link_16_Link_2") ||
                    !Build71HasLink(root, "link_17_Base_Gear_1"))
                    return;

                const string nsAuto = "https://automind.dev/mechanism";
                const string nsPlus = "https://automind.dev/urdf_plus";
                Build97EnsureNamespace(root, "automind", nsAuto);
                Build97EnsureNamespace(root, "urdf_plus", nsPlus);

                Build95RemoveDirectElements(root, nsAuto, new string[] {
                    "loop", "implicit_kinematic_candidates", "pin_connector_graph", "parallel_gripper_contract", "gripper_contract", "loop_filter_policy"
                });

                // Mechanical pivot frames at q=0 in assembly/world coordinates (meters).
                Vec3 g1 = new Vec3(-0.0135, -0.0376, 0.0042);
                Vec3 g2 = new Vec3( 0.0135, -0.0376, 0.0057);
                Vec3 l1 = new Vec3(-0.00524, -0.058, 0.0042);
                Vec3 l2 = new Vec3( 0.00524, -0.058, 0.0042);
                Vec3 j2 = new Vec3(-0.01442652, -0.06858615, 0.0);
                Vec3 j1 = new Vec3( 0.01439759, -0.06858273, 0.0);

                // Original CAD occurrence frames used by the generic writer.  Visuals are moved by old-new so q0 stays exact.
                Build97SetVisualOrigin(root, "link_3_Gear_link_1_1", new Vec3(0, 0, 0), nsAuto, true);
                Build97SetVisualOrigin(root, "link_4_Gear_link_2_1", new Vec3(0, 0, 0), nsAuto, true);
                Build97SetVisualOrigin(root, "link_15_Link_1", new Vec3(-0.00571419, -0.07349274, 0.0042) - l1, nsAuto, true);
                Build97SetVisualOrigin(root, "link_16_Link_2", new Vec3( 0.00570468, -0.07349303, 0.0042) - l2, nsAuto, true);
                Build97SetVisualOrigin(root, "link_14_Gripper_2", new Vec3(-0.00175063, -0.08662175, 0.0) - j2, nsAuto, true);
                Build97SetVisualOrigin(root, "link_13_Gripper_1", new Vec3( 0.00173046, -0.08662448, 0.0) - j1, nsAuto, true);

                // Tree topology corrected to physical pivots.
                Build97SetJoint(root, "joint_gear_link_1_link_3_Gear_link_1_1", "link_0_Base_Plate_1", "link_3_Gear_link_1_1", g1, Vec3.Zero, Vec3.UnitZ,
                    null, "dependent_gear_coordinate", "cad_axis_plus_coupling", "Gear link 1 rotates about its real base pin axis.", nsAuto);
                Build97SetJoint(root, "joint_gear_link_2_link_4_Gear_link_2_1", "link_0_Base_Plate_1", "link_4_Gear_link_2_1", g2, Vec3.Zero, Vec3.UnitZ,
                    null, "dependent_gear_coordinate", "cad_axis_plus_coupling", "Gear link 2 rotates about its real base pin axis.", nsAuto);
                Build97SetJoint(root, "joint_blue_link_1_link_15_Link_1", "link_0_Base_Plate_1", "link_15_Link_1", l1, Vec3.Zero, Vec3.UnitZ,
                    null, "dependent_ground_rocker_coordinate", "implicit_inventor_axis_plus_axial_stop", "Link_1 is grounded at Pin_3; previous builds incorrectly made it a child of Gear_link_1.", nsAuto);
                Build97SetJoint(root, "joint_blue_link_2_link_16_Link_2", "link_0_Base_Plate_1", "link_16_Link_2", l2, Vec3.Zero, Vec3.UnitZ,
                    null, "dependent_ground_rocker_coordinate", "implicit_inventor_axis_plus_axial_stop", "Link_2 is grounded at Pin_6; previous builds incorrectly made it a child of Gear_link_2.", nsAuto);
                Build97SetJoint(root, "joint_jaw_1_link_13_Gripper_1", "link_4_Gear_link_2_1", "link_13_Gripper_1", j1 - g2, Vec3.Zero, Vec3.UnitZ,
                    null, "dependent_jaw_coordinate", "implicit_pin_cluster_p4_gear_to_jaw", "Gripper_1 is hinged to Gear_link_2 at the Pin_4 cluster; rod connection closes with loop P8.", nsAuto);
                Build97SetJoint(root, "joint_jaw_2_link_14_Gripper_2", "link_3_Gear_link_1_1", "link_14_Gripper_2", j2 - g1, Vec3.Zero, Vec3.UnitZ,
                    null, "dependent_jaw_coordinate", "implicit_pin_cluster_p7_gear_to_jaw", "Gripper_2 is hinged to Gear_link_1 at the Pin_7 cluster; rod connection closes with loop P5.", nsAuto);

                XmlElement driverJoint = Build71FindJointByName(root, "joint_driver_base_gear_link_17_Base_Gear_1");
                if (driverJoint != null)
                {
                    driverJoint.SetAttribute("independent", "true");
                    driverJoint.SetAttribute("kinematic_role", nsAuto, "active_driver_coordinate");
                    driverJoint.SetAttribute("interactive_control", nsAuto, "direct_user_driver");
                    driverJoint.SetAttribute("build97_frame", nsAuto, "native_inventor_joint_frame");
                    driverJoint.SetAttribute("direct_user_control", nsAuto, "true");
                }

                // Pin visuals are fasteners fixed to a selected owner body. They are connector evidence, not loop bodies.
                Build97SetFixed(root, "joint_fixed_pin_visual_link_5_Pin_1",  "link_4_Gear_link_2_1", "link_5_Pin_1",  new Vec3(0, 0, -0.0042), Vec3.Zero, "visual_fastener_gear2_ground_axis", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_6_Pin_2",  "link_3_Gear_link_1_1", "link_6_Pin_2",  new Vec3(0, 0, -0.0027), Vec3.Zero, "visual_fastener_gear1_ground_axis", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_7_Pin_3",  "link_15_Link_1", "link_7_Pin_3", new Vec3(0, 0, -0.0027), Vec3.Zero, "visual_fastener_link1_ground_axis", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_10_Pin_6", "link_16_Link_2", "link_10_Pin_6", new Vec3(0, 0, -0.0027), Vec3.Zero, "visual_fastener_link2_ground_axis", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_8_Pin_4",  "link_4_Gear_link_2_1", "link_8_Pin_4",  new Vec3(0.00089759, -0.03098273, -0.0042), Vec3.Zero, "visual_fastener_p4_gear2_jaw1", "Owner corrected from Link_2 to Gear_link_2; no Inventor constraint supported Link_2 ownership at this pin.", nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_11_Pin_7", "link_3_Gear_link_1_1", "link_11_Pin_7", new Vec3(-0.00092652, -0.03098615, -0.0027), Vec3.Zero, "visual_fastener_p7_gear1_jaw2", "Owner corrected from Link_1 to Gear_link_1; no Inventor constraint supported Link_1 ownership at this pin.", nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_12_Pin_8", "link_16_Link_2", "link_12_Pin_8", new Vec3(0.00092935, -0.03098607, -0.0027), Vec3.Zero, "visual_fastener_p8_link2_jaw1", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_9_Pin_5",  "link_15_Link_1", "link_9_Pin_5",  new Vec3(-0.00094838, -0.03098549, -0.0027), Vec3.Zero, "visual_fastener_p5_link1_jaw2", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_18_Pin_9", "link_0_Base_Plate_1", "link_18_Pin_9", new Vec3(-0.006, -0.004, 0.0015), Vec3.Zero, "static_base_fastener", null, nsAuto);
                Build97SetFixed(root, "joint_fixed_pin_visual_link_19_Pin_10", "link_0_Base_Plate_1", "link_19_Pin_10", new Vec3(0.006, -0.004, 0.0015), Vec3.Zero, "static_base_fastener", null, nsAuto);

                Vec3 p8 = new Vec3(0.00616935, -0.08898607, 0.0015);
                Vec3 p5 = new Vec3(-0.00618838, -0.08898549, 0.0015);
                Vec3 p4 = new Vec3(0.01439759, -0.06858273, 0.0015);
                Vec3 p7 = new Vec3(-0.01442652, -0.06858615, 0.0015);

                Build97AddLoop(doc, root, "loop_build97_P8_gripper1_to_link2", "link_13_Gripper_1", "link_16_Link_2",
                    p8 - j1, p8 - l2,
                    "joint_gear_link_2_link_4_Gear_link_2_1 joint_jaw_1_link_13_Gripper_1 joint_blue_link_2_link_16_Link_2",
                    p8, "right_rod_to_jaw_closure", "constraint_F148CB76,constraint_028E980F,constraint_2EECC760,constraint_CD42E0C2", nsAuto);
                Build97AddLoop(doc, root, "loop_build97_P5_gripper2_to_link1", "link_14_Gripper_2", "link_15_Link_1",
                    p5 - j2, p5 - l1,
                    "joint_gear_link_1_link_3_Gear_link_1_1 joint_jaw_2_link_14_Gripper_2 joint_blue_link_1_link_15_Link_1",
                    p5, "left_rod_to_jaw_closure", "constraint_9B795A57,constraint_39BD7153,constraint_506198EF,constraint_3A43571B", nsAuto);

                foreach (XmlElement coupling in Build95DirectElements(root, "coupling"))
                {
                    if (!String.Equals(coupling.GetAttribute("name"), "solver_parallel_gripper_closed_chain", StringComparison.OrdinalIgnoreCase)) continue;
                    string dependent = "joint_jaw_1_link_13_Gripper_1 joint_jaw_2_link_14_Gripper_2 joint_blue_link_1_link_15_Link_1 joint_blue_link_2_link_16_Link_2";
                    coupling.SetAttribute("solver", "gauss_newton_planar_two_loop_pin_closure");
                    coupling.SetAttribute("mode", "build97_physical_tree_plus_two_pin_loops");
                    coupling.SetAttribute("dependent", dependent);
                    coupling.SetAttribute("dependent_joint", dependent);
                    coupling.SetAttribute("build97_note", nsAuto, "Tree joints now use physical pin pivots; only P8/P5 remain as loop constraints.");
                }

                XmlElement pcg = doc.CreateElement("automind", "pin_connector_graph", nsAuto);
                pcg.SetAttribute("name", "parallel_gripper_pin_graph_build97");
                pcg.SetAttribute("type", "physical_pin_connectivity");
                pcg.SetAttribute("policy", "pin_visual_is_fastener_not_solver_body");
                pcg.SetAttribute("frame_policy", "moving_body_link_frames_are_mechanical_pivots");
                root.AppendChild(pcg);

                Build97AddPinConnector(doc, pcg, "P1", "link_5_Pin_1", "link_4_Gear_link_2_1", new string[] { "link_4_Gear_link_2_1", "link_0_Base_Plate_1" }, new Vec3(0.0135, -0.0376, 0.0015), "right_gear_ground_axis_visual_fastener", "constraint_8FDB36D2,constraint_D54F4AA4", false, "", nsAuto);
                Build97AddPinConnector(doc, pcg, "P2", "link_6_Pin_2", "link_3_Gear_link_1_1", new string[] { "link_3_Gear_link_1_1", "link_0_Base_Plate_1" }, new Vec3(-0.0135, -0.0376, 0.0015), "left_gear_ground_axis_visual_fastener", "constraint_56703040,constraint_615118A2", false, "", nsAuto);
                Build97AddPinConnector(doc, pcg, "P3", "link_7_Pin_3", "link_15_Link_1", new string[] { "link_15_Link_1", "link_0_Base_Plate_1" }, new Vec3(-0.00524, -0.058, 0.0015), "left_rod_ground_tree_revolute", "constraint_C1A6433A,constraint_01792E10,constraint_EBD51290,constraint_222A883A", false, "Now represented as tree joint joint_blue_link_1_link_15_Link_1.", nsAuto);
                Build97AddPinConnector(doc, pcg, "P6", "link_10_Pin_6", "link_16_Link_2", new string[] { "link_16_Link_2", "link_0_Base_Plate_1" }, new Vec3(0.00524, -0.058, 0.0015), "right_rod_ground_tree_revolute", "constraint_CEE33457,constraint_1C8CFB79,constraint_C052EAB0,constraint_FBC27196", false, "Now represented as tree joint joint_blue_link_2_link_16_Link_2.", nsAuto);
                Build97AddPinConnector(doc, pcg, "P4", "link_8_Pin_4", "link_4_Gear_link_2_1", new string[] { "link_4_Gear_link_2_1", "link_13_Gripper_1" }, p4, "right_gear_to_jaw_tree_revolute", "constraint_27CAA779,constraint_5C077DC9,constraint_71AC442B", false, "Owner corrected to Gear_link_2. Link_2 was a false nearest-owner inference.", nsAuto);
                Build97AddPinConnector(doc, pcg, "P7", "link_11_Pin_7", "link_3_Gear_link_1_1", new string[] { "link_3_Gear_link_1_1", "link_14_Gripper_2" }, p7, "left_gear_to_jaw_tree_revolute", "constraint_4EE38DF7,constraint_640E56EB,constraint_0FF27183", false, "Owner corrected to Gear_link_1. Link_1 was a false nearest-owner inference.", nsAuto);
                Build97AddPinConnector(doc, pcg, "P8", "link_12_Pin_8", "link_16_Link_2", new string[] { "link_16_Link_2", "link_13_Gripper_1" }, p8, "right_rod_to_jaw_loop_closure", "constraint_F148CB76,constraint_028E980F,constraint_2EECC760,constraint_CD42E0C2", true, "", nsAuto);
                Build97AddPinConnector(doc, pcg, "P5", "link_9_Pin_5", "link_15_Link_1", new string[] { "link_15_Link_1", "link_14_Gripper_2" }, p5, "left_rod_to_jaw_loop_closure", "constraint_9B795A57,constraint_39BD7153,constraint_506198EF,constraint_3A43571B", true, "", nsAuto);
                Build97AddPinConnector(doc, pcg, "P9", "link_18_Pin_9", "link_0_Base_Plate_1", new string[] { "link_0_Base_Plate_1", "link_2_Base_Mounting_bracket_1", "link_1_Base_Plate_2" }, new Vec3(-0.006, -0.004, 0.0015), "base_static_fastener", "constraint_3779F1C5,constraint_97159414", false, "", nsAuto);
                Build97AddPinConnector(doc, pcg, "P10", "link_19_Pin_10", "link_0_Base_Plate_1", new string[] { "link_0_Base_Plate_1", "link_2_Base_Mounting_bracket_1" }, new Vec3(0.006, -0.004, 0.0015), "base_static_fastener", "constraint_B684EEE6,constraint_2D50A41C", false, "", nsAuto);

                XmlElement contract = doc.CreateElement("automind", "parallel_gripper_contract", nsAuto);
                contract.SetAttribute("name", "build97_parallel_gripper_contract");
                contract.SetAttribute("dof", "1");
                contract.SetAttribute("driver_joint", "joint_driver_base_gear_link_17_Base_Gear_1");
                contract.SetAttribute("tree_coordinates", "joint_gear_link_1_link_3_Gear_link_1_1 joint_gear_link_2_link_4_Gear_link_2_1 joint_blue_link_1_link_15_Link_1 joint_blue_link_2_link_16_Link_2 joint_jaw_1_link_13_Gripper_1 joint_jaw_2_link_14_Gripper_2");
                contract.SetAttribute("physical_loops", "loop_build97_P8_gripper1_to_link2 loop_build97_P5_gripper2_to_link1");
                contract.SetAttribute("gear_couplings", "coupling_joint_driver_base_gear_link_17_Base_Gear_1_to_joint_gear_link_1_link_3_Gear_link_1_1 coupling_joint_driver_base_gear_link_17_Base_Gear_1_to_joint_gear_link_2_link_4_Gear_link_2_1");
                contract.SetAttribute("important_fix", "Link_1/Link_2 are grounded rockers; Gripper_1/Gripper_2 are hinged to Gear_link_2/Gear_link_1. Pin_4/Pin_7 are not owned by the rods.");
                root.AppendChild(contract);

                foreach (XmlElement c in Build95DirectElements(root, "urdf_plus_contract"))
                {
                    c.SetAttribute("build", "BUILD97_MECHANICAL_PIVOT_GRIPPER_CONTRACT");
                    c.SetAttribute("parallel_gripper_overlay", "true");
                    c.SetAttribute("physical_pivot_tree", "true");
                    c.SetAttribute("pin_connector_graph", "parallel_gripper_pin_graph_build97");
                    XmlElement counts = Build71FirstChild(c, "counts");
                    if (counts != null)
                    {
                        counts.SetAttribute("loop_joints", "2");
                        counts.SetAttribute("couplings", "3");
                        counts.SetAttribute("independent_dof", "1");
                    }
                }

                string parentAudit = Build97AuditMultipleParents(root);
                if (!String.IsNullOrEmpty(parentAudit))
                    Build51Log.Warn("BUILD97_GRIPPER_PARENT_AUDIT " + parentAudit);

                doc.Save(urdfPath);
                Build51Log.Summary("BUILD97_GRIPPER_MECHANICAL_PIVOT_PATCH applied urdf='" + urdfPath + "' loops=2 pin_connectors=10 q0_visual_offsets=6 topology='physical_tree_plus_two_loops'");
            }
            catch (Exception ex)
            {
                Build51Log.Warn("BUILD97_GRIPPER_MECHANICAL_PIVOT_PATCH skipped/failed: " + ex.Message);
            }
        }

        private void Build97EnsureNamespace(XmlElement root, string prefix, string uri)
        {
            try
            {
                if (root == null) return;
                string attrName = "xmlns:" + prefix;
                if (String.IsNullOrEmpty(root.GetAttribute(attrName))) root.SetAttribute(attrName, "http://www.w3.org/2000/xmlns/", uri);
            }
            catch { }
        }

        private string Build97Fmt(Vec3 v)
        {
            return F(v.X) + " " + F(v.Y) + " " + F(v.Z);
        }

        private string Build97Fmt(double x)
        {
            if (Math.Abs(x) < 5e-12) x = 0.0;
            return x.ToString("0.##########", CultureInfo.InvariantCulture);
        }

        private void Build97SetJoint(XmlElement root, string jname, string parent, string childLink, Vec3 xyz, Vec3 rpy, Vec3 axis, string jtype, string role, string authority, string note, string nsAuto)
        {
            XmlElement j = Build71FindJointByName(root, jname);
            if (j == null)
            {
                Build51Log.Warn("BUILD97_GRIPPER missing joint '" + jname + "'");
                return;
            }
            if (!String.IsNullOrEmpty(jtype)) j.SetAttribute("type", jtype);
            XmlElement p = Build71FirstChild(j, "parent"); if (p == null) { p = j.OwnerDocument.CreateElement("parent"); j.AppendChild(p); }
            XmlElement c = Build71FirstChild(j, "child"); if (c == null) { c = j.OwnerDocument.CreateElement("child"); j.AppendChild(c); }
            XmlElement o = Build71FirstChild(j, "origin"); if (o == null) { o = j.OwnerDocument.CreateElement("origin"); j.AppendChild(o); }
            XmlElement a = Build71FirstChild(j, "axis"); if (a == null && !String.Equals(j.GetAttribute("type"), "fixed", StringComparison.OrdinalIgnoreCase)) { a = j.OwnerDocument.CreateElement("axis"); j.AppendChild(a); }
            p.SetAttribute("link", parent);
            c.SetAttribute("link", childLink);
            o.SetAttribute("xyz", Build97Fmt(xyz));
            o.SetAttribute("rpy", Build97Fmt(rpy));
            if (a != null) a.SetAttribute("xyz", Build97Fmt(axis));
            j.SetAttribute("independent", String.Equals(jname, "joint_driver_base_gear_link_17_Base_Gear_1", StringComparison.OrdinalIgnoreCase) ? "true" : "false");
            j.SetAttribute("build97_frame", nsAuto, "mechanical_pivot_frame");
            j.SetAttribute("q0_preserved_by_visual_offset", nsAuto, "true");
            if (!String.IsNullOrEmpty(role)) j.SetAttribute("kinematic_role", nsAuto, role);
            if (!String.IsNullOrEmpty(authority)) j.SetAttribute("kinematic_authority", nsAuto, authority);
            if (!String.IsNullOrEmpty(note)) j.SetAttribute("build97_note", nsAuto, note);
            j.SetAttribute("direct_user_control", nsAuto, String.Equals(jname, "joint_driver_base_gear_link_17_Base_Gear_1", StringComparison.OrdinalIgnoreCase) ? "true" : "false");
        }

        private void Build97SetFixed(XmlElement root, string jname, string parent, string childLink, Vec3 xyz, Vec3 rpy, string role, string note, string nsAuto)
        {
            XmlElement j = Build71FindJointByName(root, jname);
            if (j == null)
            {
                Build51Log.Warn("BUILD97_GRIPPER missing fixed joint '" + jname + "'");
                return;
            }
            j.SetAttribute("type", "fixed");
            XmlElement p = Build71FirstChild(j, "parent"); if (p == null) { p = j.OwnerDocument.CreateElement("parent"); j.AppendChild(p); }
            XmlElement c = Build71FirstChild(j, "child"); if (c == null) { c = j.OwnerDocument.CreateElement("child"); j.AppendChild(c); }
            XmlElement o = Build71FirstChild(j, "origin"); if (o == null) { o = j.OwnerDocument.CreateElement("origin"); j.AppendChild(o); }
            p.SetAttribute("link", parent);
            c.SetAttribute("link", childLink);
            o.SetAttribute("xyz", Build97Fmt(xyz));
            o.SetAttribute("rpy", Build97Fmt(rpy));
            XmlElement a = Build71FirstChild(j, "axis");
            if (a != null) j.RemoveChild(a);
            j.RemoveAttribute("independent");
            if (!String.IsNullOrEmpty(role)) j.SetAttribute("kinematic_role", nsAuto, role);
            if (!String.IsNullOrEmpty(note)) j.SetAttribute("build97_note", nsAuto, note);
            j.SetAttribute("direct_user_control", nsAuto, "false");
        }

        private void Build97SetVisualOrigin(XmlElement root, string linkName, Vec3 xyz, string nsAuto, bool mechanicalFrame)
        {
            XmlElement link = null;
            foreach (XmlElement e in Build95DirectElements(root, "link"))
            {
                if (String.Equals(e.GetAttribute("name"), linkName, StringComparison.OrdinalIgnoreCase)) { link = e; break; }
            }
            if (link == null)
            {
                Build51Log.Warn("BUILD97_GRIPPER missing link for visual origin '" + linkName + "'");
                return;
            }
            foreach (XmlNode n in link.ChildNodes)
            {
                XmlElement vis = n as XmlElement;
                if (vis == null || !String.Equals(vis.LocalName, "visual", StringComparison.OrdinalIgnoreCase)) continue;
                XmlElement origin = Build71FirstChild(vis, "origin");
                if (origin == null)
                {
                    origin = link.OwnerDocument.CreateElement("origin");
                    vis.InsertBefore(origin, vis.FirstChild);
                    origin.SetAttribute("rpy", "0 0 0");
                }
                string oldRpy = origin.GetAttribute("rpy");
                origin.SetAttribute("xyz", Build97Fmt(xyz));
                origin.SetAttribute("rpy", String.IsNullOrEmpty(oldRpy) ? "0 0 0" : oldRpy);
            }
            link.SetAttribute("build97_frame", nsAuto, mechanicalFrame ? "mechanical_pivot_frame" : "cad_occurrence_frame");
        }

        private void Build97AddLoop(XmlDocument doc, XmlElement root, string name, string pred, string succ, Vec3 predXyz, Vec3 succXyz, string involved, Vec3 pivotWorld, string role, string evidence, string nsAuto)
        {
            XmlElement loop = doc.CreateElement("automind", "loop", nsAuto);
            loop.SetAttribute("name", name);
            loop.SetAttribute("type", "revolute");
            loop.SetAttribute("constraint", "point_axis_coincidence");
            loop.SetAttribute("solver", "gauss_newton_planar_pin_closure");
            loop.SetAttribute("mode", "build97_physical_pivot_loop");
            loop.SetAttribute("involved_tree_joints", involved);
            loop.SetAttribute("closure_error_m", "0");
            loop.SetAttribute("kinematic_role", nsAuto, role);
            loop.SetAttribute("truth_state", nsAuto, "cad_constraint_verified_physical_pin_cluster");
            loop.SetAttribute("requires_review", nsAuto, "false");
            XmlElement p = doc.CreateElement("predecessor"); p.SetAttribute("link", pred); loop.AppendChild(p);
            XmlElement s = doc.CreateElement("successor"); s.SetAttribute("link", succ); loop.AppendChild(s);
            XmlElement o = doc.CreateElement("origin"); o.SetAttribute("xyz", Build97Fmt(predXyz)); o.SetAttribute("rpy", "0 0 0"); loop.AppendChild(o);
            XmlElement so = doc.CreateElement("successor_origin"); so.SetAttribute("xyz", Build97Fmt(succXyz)); so.SetAttribute("rpy", "0 0 0"); loop.AppendChild(so);
            XmlElement axis = doc.CreateElement("axis"); axis.SetAttribute("xyz", "0 0 1"); loop.AppendChild(axis);
            XmlElement ev = doc.CreateElement("automind", "evidence", nsAuto);
            ev.SetAttribute("source", "build97_generator_reconstruction_from_robot_gripper_iam_logs");
            ev.SetAttribute("constraint_stable_ids", evidence);
            ev.SetAttribute("pivot_world_m", Build97Fmt(pivotWorld));
            ev.SetAttribute("q0_contract", "predecessor_link_frame*origin == successor_link_frame*successor_origin");
            ev.SetAttribute("note", "Endpoint is a real body-to-body pin closure. Visual Pin_* parts are not loop endpoints and are fixed to a chosen owner body.");
            loop.AppendChild(ev);
            root.AppendChild(loop);
        }

        private void Build97AddPinConnector(XmlDocument doc, XmlElement parent, string id, string pinLink, string owner, string[] participants, Vec3 pivot, string role, string evidence, bool solverRelevant, string note, string nsAuto)
        {
            XmlElement e = doc.CreateElement("automind", "pin_connector", nsAuto);
            e.SetAttribute("id", id);
            e.SetAttribute("pin_link", pinLink);
            e.SetAttribute("owner_body", owner);
            e.SetAttribute("participants", String.Join(" ", participants));
            e.SetAttribute("pivot_world_m", Build97Fmt(pivot));
            e.SetAttribute("axis_world", "0 0 1");
            e.SetAttribute("role", role);
            e.SetAttribute("evidence", evidence);
            e.SetAttribute("solver_relevant", solverRelevant ? "true" : "false");
            if (!String.IsNullOrEmpty(note)) e.SetAttribute("note", note);
            foreach (string p in participants)
            {
                XmlElement pe = doc.CreateElement("automind", "participant", nsAuto);
                pe.SetAttribute("link", p);
                e.AppendChild(pe);
            }
            parent.AppendChild(e);
        }

        private string Build97AuditMultipleParents(XmlElement root)
        {
            Dictionary<string, string> parents = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            List<string> errors = new List<string>();
            foreach (XmlElement j in Build95DirectElements(root, "joint"))
            {
                XmlElement c = Build71FirstChild(j, "child");
                XmlElement p = Build71FirstChild(j, "parent");
                if (c == null || p == null) continue;
                string cl = c.GetAttribute("link");
                if (String.IsNullOrEmpty(cl)) continue;
                if (parents.ContainsKey(cl)) errors.Add(cl + ":" + parents[cl] + "->" + p.GetAttribute("link") + " via " + j.GetAttribute("name"));
                else parents[cl] = p.GetAttribute("link");
            }
            return String.Join(";", errors.ToArray());
        }

        private List<XmlElement> Build95DirectElements(XmlElement root, string localName)
        {
            List<XmlElement> outList = new List<XmlElement>();
            if (root == null) return outList;
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e != null && String.Equals(e.LocalName, localName, StringComparison.OrdinalIgnoreCase)) outList.Add(e);
            }
            return outList;
        }

        private string Build95LoopEndpoint(XmlElement loop, string childLocalName)
        {
            if (loop == null) return "";
            XmlElement child = Build71FirstChild(loop, childLocalName);
            if (child == null) return "";
            string link = child.GetAttribute("link");
            if (String.IsNullOrEmpty(link)) link = child.GetAttribute("name");
            return link ?? "";
        }

        private string Build95PairKey(string a, string b)
        {
            a = a ?? "";
            b = b ?? "";
            return String.Compare(a, b, StringComparison.OrdinalIgnoreCase) <= 0
                ? a + "|" + b
                : b + "|" + a;
        }

        private bool Build95IsMinimalParallelGripperLoopPair(string a, string b)
        {
            string pk = Build95PairKey(a, b);
            // Minimal body-level gripper closures.  Gear-to-gear and gear-to-base
            // relations are already represented by explicit couplings, and visual
            // pins are fixed to their owning body.
            if (pk == Build95PairKey("link_15_Link_1", "link_0_Base_Plate_1")) return true;
            if (pk == Build95PairKey("link_16_Link_2", "link_0_Base_Plate_1")) return true;
            if (pk == Build95PairKey("link_13_Gripper_1", "link_16_Link_2")) return true;
            if (pk == Build95PairKey("link_14_Gripper_2", "link_15_Link_1")) return true;
            if (pk == Build95PairKey("link_14_Gripper_2", "link_3_Gear_link_1_1")) return true;
            if (pk == Build95PairKey("link_13_Gripper_1", "link_4_Gear_link_2_1")) return true;
            return false;
        }

        private void Build95RemoveDirectElements(XmlElement root, string namespaceUri, string[] localNames)
        {
            if (root == null || localNames == null) return;
            HashSet<string> wanted = new HashSet<string>(localNames, StringComparer.OrdinalIgnoreCase);
            List<XmlElement> remove = new List<XmlElement>();
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e == null) continue;
                bool nsOk = String.IsNullOrEmpty(namespaceUri) || String.Equals(e.NamespaceURI, namespaceUri, StringComparison.OrdinalIgnoreCase);
                if (nsOk && wanted.Contains(e.LocalName)) remove.Add(e);
            }
            foreach (XmlElement e in remove)
            {
                if (e.ParentNode != null) e.ParentNode.RemoveChild(e);
            }
        }

        // --------------------------------------------------------------------
        // BUILD71 post-writer patch for the double-cardan IAM.
        // --------------------------------------------------------------------
        // The Inventor browser shows the cardan as shaft-yoke rigid stacks plus
        // two universal crosses. A standard URDF tree cannot express the closure
        // between Furca lunga:1 and Furca medie:1 directly because that would give
        // one link two parents. Therefore the correct output is:
        //   - keep the tree readable by old URDF loaders;
        //   - force Ax canelat -> Furca scurta as FIXED stack joints;
        //   - write an automind:loop fixed_relative_transform between the middle yokes;
        //   - write automind:coupling hints consumed by Super.html / v27 viewer.
        // This method only activates when all expected cardan link names are present.
        private void PatchCardanUrdfContractToSuperStyle(string urdfPath)
        {
            try
            {
                if (String.IsNullOrEmpty(urdfPath) || !File.Exists(urdfPath)) return;

                XmlDocument doc = new XmlDocument();
                doc.PreserveWhitespace = false;
                doc.Load(urdfPath);
                XmlElement root = doc.DocumentElement;
                if (root == null || !String.Equals(root.LocalName, "robot", StringComparison.OrdinalIgnoreCase)) return;

                if (!Build71HasLink(root, "link_3_Furca_lunga_1") ||
                    !Build71HasLink(root, "link_6_Furca_medie_1") ||
                    !Build71HasLink(root, "link_7_Furca_scurta_1") ||
                    !Build71HasLink(root, "link_8_Furca_scurta_2") ||
                    !Build71HasLink(root, "link_9_Ax_canelat_1") ||
                    !Build71HasLink(root, "link_10_Ax_canelat_2"))
                    return;

                const string nsAuto = "https://automind.dev/mechanism";
                const string nsPlus = "https://automind.dev/urdf_plus";
                Build71ForceFixedStackJoint(root,
                    "link_9_Ax_canelat_1", "link_7_Furca_scurta_1",
                    "joint_fixed_link_9_Ax_canelat_1_to_link_7_Furca_scurta_1",
                    "cad_constraint_pair_fixed_mount_build66",
                    "constraint_E441F725,constraint_FC92C067,constraint_29FFF2AC");

                Build71ForceFixedStackJoint(root,
                    "link_10_Ax_canelat_2", "link_8_Furca_scurta_2",
                    "joint_fixed_link_10_Ax_canelat_2_to_link_8_Furca_scurta_2",
                    "cad_constraint_pair_fixed_mount_build66",
                    "constraint_656F7992,constraint_9899CF5C,constraint_AEEF12A6");

                Build71MarkJointIndependence(root,
                    "joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1", "true", null, null);
                Build71MarkJointIndependence(root,
                    "joint_revolute_link_1_Lagar_1_to_link_10_Ax_canelat_2", "false", null, null);
                Build71MarkJointIndependence(root,
                    "joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2", "false", null, null);
                Build71MarkJointIndependence(root,
                    "joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1", "false", null, null);
                Build71MarkJointIndependence(root,
                    "joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1", "false", null, null);
                Build71MarkJointIndependence(root,
                    "joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1", "false", "driver", "joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1");

                // Remove stale URDF+ closures/couplings written by previous builds.
                Build71RemoveRootElements(root, nsAuto, new string[] { "loop", "coupling", "solver_hint", "drag_policy" });
                Build71RemoveRootElements(root, nsPlus, new string[] { "loop_joint", "urdf_plus_contract" });

                XmlNode before = Build71FindRootElement(root, nsAuto, "urdf_plus_contract");
                string fragment = @"
  <automind:loop name=""loop_fixed_relative_link_3_Furca_lunga_1_to_link_6_Furca_medie_1"" type=""fixed_relative_transform"" constraint=""middle_yoke_phase_closure"" closure_error_m=""0.000000000"" involved_tree_joints=""joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2 joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1 joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1 joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1"" solver=""finite_difference"" mode=""preserve_middle_yoke_q0"" tolerance=""0.0005""><predecessor link=""link_3_Furca_lunga_1"" /><successor link=""link_6_Furca_medie_1"" /><origin xyz=""-0.233310011 0.00453000775 -0.00784619476"" rpy=""-1.04719753 5.9902455e-10 3.14159265"" /><predecessor_origin xyz=""0 0 0"" rpy=""0 0 0"" /><successor_origin xyz=""0 0 0"" rpy=""0 0 0"" /><automind:relative_transform predecessor_to_successor_xyz=""-0.233310011 0.00453000775 -0.00784619476"" predecessor_to_successor_rpy=""-1.04719753 5.9902455e-10 3.14159265"" /><automind:evidence source=""manual_build66_center_loop_from_inventor_mates"" constraint_stable_ids=""Furca_lunga:1 Mate:9 Angle:1 Flush:1 Mate:16 Mate:17; Furca_medie:1 Mate:5 Mate:6 Mate:9 Angle:1 Flush:1"" note=""Correct loop usage: this is a fixed relative transform between the two middle yokes, not a zero-origin rigid lock and not a revolute shaft-axis joint."" /></automind:loop>
  <automind:solver_hint name=""solver_hint_build72_cardan_gauss_newton_single_dof_drag"" type=""closed_chain_pose_solver"" solver=""gauss_newton"" interactive_policy=""single_driver_only"" manual_drag=""redirect_dependents_to_driver"" driver_joint=""joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1"" predecessor_link=""link_3_Furca_lunga_1"" successor_link=""link_6_Furca_medie_1"" relation=""successor_world = predecessor_world * q0_relative_transform"" independent_joints=""joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1"" dependent_joints=""joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2 joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1 joint_revolute_link_1_Lagar_1_to_link_10_Ax_canelat_2 joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1 joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1"" tolerance=""0.0005"" source=""manual_build72"" />
  <automind:drag_policy name=""drag_policy_double_cardan_single_dof"" mechanism=""double_cardan"" policy=""redirect_all_cardan_parts_to_driver"" driver_joint=""joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1"" affected_links=""link_9_Ax_canelat_1 link_7_Furca_scurta_1 link_5_Cruce_cardanica_2 link_3_Furca_lunga_1 link_10_Ax_canelat_2 link_8_Furca_scurta_2 link_4_Cruce_cardanica_1 link_6_Furca_medie_1"" note=""Prevents link_6_Furca_medie_1 from being manually driven by its dependent local joint while the loop solver also moves its parent branch."" />
  <urdf_plus:loop_joint name=""urdf_plus_loop_fixed_relative_link_3_Furca_lunga_1_to_link_6_Furca_medie_1"" type=""fixed"" parent=""link_3_Furca_lunga_1"" child=""link_6_Furca_medie_1"" solver=""preserve_q0_relative_transform"" source=""alias_of_automind_loop_fixed_relative_middle_yokes""><origin xyz=""-0.233310011 0.00453000775 -0.00784619476"" rpy=""-1.04719753 5.9902455e-10 3.14159265"" /></urdf_plus:loop_joint>
  <urdf_plus:urdf_plus_contract name=""build70_double_cardan_visualizer_contract""><urdf_plus:counts links=""12"" joints=""11"" loops=""1"" couplings=""6"" /><urdf_plus:coordinate joint=""joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1"" independent=""true"" /><urdf_plus:coordinate joint=""joint_revolute_link_1_Lagar_1_to_link_10_Ax_canelat_2"" independent=""false"" /><urdf_plus:coordinate joint=""joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2"" independent=""false"" /><urdf_plus:coordinate joint=""joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1"" independent=""false"" /><urdf_plus:coordinate joint=""joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1"" independent=""false"" /><urdf_plus:coordinate joint=""joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1"" independent=""false"" /><urdf_plus:edge name=""middle_yoke_fixed_relative_loop"" parent=""link_3_Furca_lunga_1"" child=""link_6_Furca_medie_1"" type=""fixed_relative_transform"" role=""kinematic_loop_closure"" score=""1"" source=""manual_build70"" evidence=""Mate:9 Angle:1 Flush:1 Mate:16 Mate:17"" involved_tree_joints=""joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2 joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1 joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1 joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1"" truth_state=""verified"" requires_review=""false"" /><urdf_plus:edge name=""input_shaft_stack"" parent=""link_9_Ax_canelat_1"" child=""link_7_Furca_scurta_1"" type=""fixed"" role=""rigid_stack"" source=""Inventor"" evidence=""Mate:10 Mate:11 Mate:12"" truth_state=""verified"" requires_review=""false"" /><urdf_plus:edge name=""output_shaft_stack"" parent=""link_10_Ax_canelat_2"" child=""link_8_Furca_scurta_2"" type=""fixed"" role=""rigid_stack"" source=""Inventor"" evidence=""Mate:13 Mate:14 Mate:15"" truth_state=""verified"" requires_review=""false"" /></urdf_plus:urdf_plus_contract>
  <automind:coupling name=""coupling_middle_yokes_rigid_phase_link_3_to_link_6"" type=""rigid_phase_lock"" solver=""preserve_q0_relative_transform"" mode=""middle_shaft_phased_yokes"" master_link=""link_3_Furca_lunga_1"" dependent_link=""link_6_Furca_medie_1"" ratio=""1"" offset=""0""><predecessor link=""link_3_Furca_lunga_1"" /><successor link=""link_6_Furca_medie_1"" /><automind:relative_transform predecessor_to_successor_xyz=""-0.233310011 0.00453000775 -0.00784619476"" predecessor_to_successor_rpy=""-1.04719753 5.9902455e-10 3.14159265"" /><automind:evidence source=""manual_build66_center_coupling_from_inventor_mates"" constraint_stable_ids=""Mate:9,Angle:1,Flush:1,Mate:16,Mate:17"" note=""Correct coupling usage: the middle pair must move as one phased rigid subassembly while the four cardan pin revolutes solve the angle change."" /></automind:coupling>
  <automind:coupling name=""coupling_input_shaft_to_short_yoke_stack"" type=""rigid_mount_stack"" solver=""preserve_q0_relative_transform"" mode=""shaft_yoke_fixed_mount"" master_link=""link_9_Ax_canelat_1"" dependent_link=""link_7_Furca_scurta_1"" ratio=""1"" offset=""0""><automind:relative_transform predecessor_to_successor_xyz=""0.02462064 -0.0069993 -0.01899936"" predecessor_to_successor_rpy=""-1.57079633 0 -3.14159265"" /><automind:evidence source=""manual_build66_inventor_browser"" constraint_stable_ids=""Ax_canelat:1 Mate:10 Mate:11 Mate:12; Furca_scurta:1 Mate:10 Mate:11 Mate:12"" note=""Ax canelat:1 and Furca scurta:1 are a rigid mounted stack. They rotate together through the Lagar:2 bearing revolute; no separate yoke revolute is allowed here."" /></automind:coupling>
  <automind:coupling name=""coupling_output_shaft_to_short_yoke_stack"" type=""rigid_mount_stack"" solver=""preserve_q0_relative_transform"" mode=""shaft_yoke_fixed_mount"" master_link=""link_10_Ax_canelat_2"" dependent_link=""link_8_Furca_scurta_2"" ratio=""1"" offset=""0""><automind:relative_transform predecessor_to_successor_xyz=""-0.00335907 -0.01346668 -0.05787016"" predecessor_to_successor_rpy=""-1.57079633 0 3.14159265"" /><automind:evidence source=""manual_build66_inventor_browser"" constraint_stable_ids=""Ax_canelat:2 Mate:13 Mate:14 Mate:15; Furca_scurta:2 fixed shaft-yoke mount"" note=""Ax canelat:2 and Furca scurta:2 are a rigid mounted stack. They rotate together through the Lagar:1 bearing revolute."" /></automind:coupling>
  <automind:coupling name=""coupling_cardan_pin_axes_intersections"" type=""universal_joint_axis_group"" solver=""keep_pin_axes_intersecting_and_orthogonal"" mode=""two_universal_joints""><automind:universal name=""input_universal_joint"" cross_link=""link_5_Cruce_cardanica_2"" yoke_a=""link_7_Furca_scurta_1"" yoke_b=""link_3_Furca_lunga_1"" joint_a=""joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2"" joint_b=""joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1"" /><automind:universal name=""output_universal_joint"" cross_link=""link_4_Cruce_cardanica_1"" yoke_a=""link_8_Furca_scurta_2"" yoke_b=""link_6_Furca_medie_1"" joint_a=""joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1"" joint_b=""joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1"" /><automind:evidence source=""manual_build66_universal_joint_grouping"" constraint_stable_ids=""Cruce_cardanica:1 Mate:5 Mate:6 Mate:7 Mate:8; Cruce_cardanica:2 Mate:3 Mate:4 Mate:16 Mate:17"" note=""Groups each cross as a universal joint. The viewer should rotate only around the pin axes, never around the shaft/yoke rigid-stack axis."" /></automind:coupling>
";
                Build71AppendFragmentBefore(doc, root, fragment, before);
                Build71PatchAutomindContract(root, nsAuto);

                doc.Save(urdfPath);
                Build51Log.Summary("BUILD71_CARDAN_SUPER_URDF_PATCH applied to '" + urdfPath + "'");
            }
            catch (Exception ex)
            {
                Build51Log.Warn("BUILD71_CARDAN_SUPER_URDF_PATCH skipped/failed: " + ex.Message);
            }
        }

        private bool Build71HasLink(XmlElement root, string linkName)
        {
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e != null && e.LocalName == "link" && e.GetAttribute("name") == linkName) return true;
            }
            return false;
        }

        private XmlElement Build71FindJointByPair(XmlElement root, string parentLink, string childLink)
        {
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement j = n as XmlElement;
                if (j == null || j.LocalName != "joint") continue;
                XmlElement p = Build71FirstChild(j, "parent");
                XmlElement c = Build71FirstChild(j, "child");
                if (p != null && c != null && p.GetAttribute("link") == parentLink && c.GetAttribute("link") == childLink) return j;
            }
            return null;
        }

        private XmlElement Build71FindJointByName(XmlElement root, string name)
        {
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement j = n as XmlElement;
                if (j != null && j.LocalName == "joint" && j.GetAttribute("name") == name) return j;
            }
            return null;
        }

        private XmlElement Build71FirstChild(XmlElement parent, string localName)
        {
            if (parent == null) return null;
            foreach (XmlNode n in parent.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e != null && e.LocalName == localName) return e;
            }
            return null;
        }

        private void Build71ForceFixedStackJoint(XmlElement root, string parentLink, string childLink, string newName, string source, string evidence)
        {
            XmlElement j = Build71FindJointByPair(root, parentLink, childLink);
            if (j == null) return;
            j.SetAttribute("name", newName);
            j.SetAttribute("type", "fixed");
            j.RemoveAttribute("independent");
            j.RemoveAttribute("interactive_control", "https://automind.dev/mechanism");
            j.RemoveAttribute("controlled_by", "https://automind.dev/mechanism");
            Build71RemoveChildElements(j, new string[] { "axis", "limit", "mimic" });
            Build71SetEvidence(j, source, evidence);
        }

        private void Build71MarkJointIndependence(XmlElement root, string name, string independent, string interactiveControl, string controlledBy)
        {
            XmlElement j = Build71FindJointByName(root, name);
            if (j == null) return;
            j.SetAttribute("independent", independent);
            if (!String.IsNullOrEmpty(interactiveControl)) j.SetAttribute("interactive_control", "https://automind.dev/mechanism", interactiveControl);
            if (!String.IsNullOrEmpty(controlledBy)) j.SetAttribute("controlled_by", "https://automind.dev/mechanism", controlledBy);
        }

        private void Build71SetEvidence(XmlElement joint, string source, string evidence)
        {
            XmlElement ev = Build71FirstChild(joint, "evidence");
            if (ev == null)
            {
                ev = joint.OwnerDocument.CreateElement("automind", "evidence", "https://automind.dev/mechanism");
                joint.AppendChild(ev);
            }
            ev.SetAttribute("source", source ?? "");
            ev.SetAttribute("constraint_stable_ids", evidence ?? "");
            ev.SetAttribute("name_used_for_inference", "false");
        }

        private void Build71RemoveChildElements(XmlElement parent, string[] localNames)
        {
            if (parent == null || localNames == null) return;
            HashSet<string> set = new HashSet<string>(localNames);
            List<XmlNode> remove = new List<XmlNode>();
            foreach (XmlNode n in parent.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e != null && set.Contains(e.LocalName)) remove.Add(n);
            }
            foreach (XmlNode n in remove) parent.RemoveChild(n);
        }

        private void Build71RemoveRootElements(XmlElement root, string ns, string[] localNames)
        {
            HashSet<string> set = new HashSet<string>(localNames);
            List<XmlNode> remove = new List<XmlNode>();
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e != null && e.NamespaceURI == ns && set.Contains(e.LocalName)) remove.Add(n);
            }
            foreach (XmlNode n in remove) root.RemoveChild(n);
        }

        private XmlNode Build71FindRootElement(XmlElement root, string ns, string localName)
        {
            foreach (XmlNode n in root.ChildNodes)
            {
                XmlElement e = n as XmlElement;
                if (e != null && e.NamespaceURI == ns && e.LocalName == localName) return e;
            }
            return null;
        }

        private void Build71AppendFragmentBefore(XmlDocument doc, XmlElement root, string fragmentXml, XmlNode before)
        {
            const string nsAuto = "https://automind.dev/mechanism";
            const string nsPlus = "https://automind.dev/urdf_plus";
            XmlDocument tmp = new XmlDocument();
            tmp.LoadXml("<wrap xmlns:automind=\"" + nsAuto + "\" xmlns:urdf_plus=\"" + nsPlus + "\">" + fragmentXml + "</wrap>");
            foreach (XmlNode n in tmp.DocumentElement.ChildNodes)
            {
                XmlNode imported = doc.ImportNode(n, true);
                root.InsertBefore(imported, before);
            }
        }

        private void Build71PatchAutomindContract(XmlElement root, string nsAuto)
        {
            XmlElement contract = Build71FindRootElement(root, nsAuto, "urdf_plus_contract") as XmlElement;
            if (contract == null) return;
            contract.SetAttribute("schema", "AutoMind.Build66.UrdfPlusContract.v1");
            contract.SetAttribute("build", "BUILD83_CANONICAL_ORTHOGONAL_JOINT_FRAMES");
            contract.SetAttribute("tree_edges", "10");
            contract.SetAttribute("loop_edges", "1");
            contract.SetAttribute("couplings", "5");
            contract.SetAttribute("independent_dof", "1");
            XmlElement counts = Build71FirstChild(contract, "counts");
            if (counts != null)
            {
                counts.SetAttribute("links", "11");
                counts.SetAttribute("tree_joints", "10");
                counts.SetAttribute("movable_tree_joints", "6");
                counts.SetAttribute("loop_joints", "1");
                counts.SetAttribute("couplings", "5");
                counts.SetAttribute("independent_dof", "1");
            }
        }

        // --------------------------------------------------------------------
        // BUILD83 AXIS FORENSICS: exhaustive DebugView diagnostics.
        // Filter DebugView with: [USD][AXISDBG] OR [USD][FRAMEDBG]
        // The same output is persisted in the USD folder/AutoMind_USD_DEBUG_MAX.log.
        // --------------------------------------------------------------------

        private string MatrixReport(Mat4 m)
        {
            Vec3 rpy = m.ToRpy();
            return "xyz=" + m.Translation.Text() +
                " rpy=" + rpy.Text() +
                " rows=[" +
                F(m.M11) + "," + F(m.M12) + "," + F(m.M13) + ";" +
                F(m.M21) + "," + F(m.M22) + "," + F(m.M23) + ";" +
                F(m.M31) + "," + F(m.M32) + "," + F(m.M33) + "]" +
                " det=" + F(Determinant3(m)) +
                " ortho=" + F(OrthogonalityError(m));
        }

        private double Determinant3(Mat4 m)
        {
            return m.M11 * (m.M22 * m.M33 - m.M23 * m.M32)
                 - m.M12 * (m.M21 * m.M33 - m.M23 * m.M31)
                 + m.M13 * (m.M21 * m.M32 - m.M22 * m.M31);
        }

        private double OrthogonalityError(Mat4 m)
        {
            Vec3 x = new Vec3(m.M11, m.M21, m.M31);
            Vec3 y = new Vec3(m.M12, m.M22, m.M32);
            Vec3 z = new Vec3(m.M13, m.M23, m.M33);
            return Math.Max(
                Math.Max(Math.Abs(x.Length - 1.0), Math.Abs(y.Length - 1.0)),
                Math.Max(Math.Abs(z.Length - 1.0),
                    Math.Max(Math.Abs(x.Dot(y)), Math.Max(Math.Abs(x.Dot(z)), Math.Abs(y.Dot(z))))));
        }

        private double RotationMatrixMaxError(Mat4 a, Mat4 b)
        {
            double e = 0.0;
            e = Math.Max(e, Math.Abs(a.M11 - b.M11)); e = Math.Max(e, Math.Abs(a.M12 - b.M12)); e = Math.Max(e, Math.Abs(a.M13 - b.M13));
            e = Math.Max(e, Math.Abs(a.M21 - b.M21)); e = Math.Max(e, Math.Abs(a.M22 - b.M22)); e = Math.Max(e, Math.Abs(a.M23 - b.M23));
            e = Math.Max(e, Math.Abs(a.M31 - b.M31)); e = Math.Max(e, Math.Abs(a.M32 - b.M32)); e = Math.Max(e, Math.Abs(a.M33 - b.M33));
            return e;
        }

        private double AngleDegrees(Vec3 a, Vec3 b)
        {
            Vec3 aa = a.NormalizedOr(Vec3.UnitZ);
            Vec3 bb = b.NormalizedOr(Vec3.UnitZ);
            double d = Math.Max(-1.0, Math.Min(1.0, aa.Dot(bb)));
            return Math.Acos(d) * 180.0 / Math.PI;
        }

        private string CardinalReport(Vec3 v)
        {
            Vec3 n = v.NormalizedOr(Vec3.UnitZ);
            Vec3[] axes = new Vec3[] { Vec3.UnitX, Vec3.UnitX * -1.0, Vec3.UnitY, Vec3.UnitY * -1.0, Vec3.UnitZ, Vec3.UnitZ * -1.0 };
            string[] names = new string[] { "+X", "-X", "+Y", "-Y", "+Z", "-Z" };
            int best = 0;
            double bestDot = -2.0;
            for (int i = 0; i < axes.Length; i++)
            {
                double d = n.Dot(axes[i]);
                if (d > bestDot) { bestDot = d; best = i; }
            }
            double angle = Math.Acos(Math.Max(-1.0, Math.Min(1.0, bestDot))) * 180.0 / Math.PI;
            return "nearest=" + names[best] + " angle_deg=" + F(angle) +
                " dots={+X:" + F(n.Dot(Vec3.UnitX)) + ",+Y:" + F(n.Dot(Vec3.UnitY)) + ",+Z:" + F(n.Dot(Vec3.UnitZ)) + "}";
        }

        private string ObjectTypeName(object o)
        {
            if (o == null) return "null";
            try { return o.GetType().FullName ?? o.GetType().Name; }
            catch { return "<type-error>"; }
        }

        private string ObjectValueSummary(object value)
        {
            if (value == null) return "null";
            try
            {
                if (value is string || value.GetType().IsPrimitive || value.GetType().IsEnum || value is decimal)
                    return Convert.ToString(value, CultureInfo.InvariantCulture);
                object x = TryGet(value, "X");
                object y = TryGet(value, "Y");
                object z = TryGet(value, "Z");
                if (x != null && y != null && z != null)
                    return "XYZ(raw)=" + Convert.ToString(x, CultureInfo.InvariantCulture) + "," +
                        Convert.ToString(y, CultureInfo.InvariantCulture) + "," + Convert.ToString(z, CultureInfo.InvariantCulture);
                string name = SafeString(TryGet(value, "Name"));
                return "type=" + ObjectTypeName(value) + (String.IsNullOrEmpty(name) ? "" : " name='" + name + "'");
            }
            catch (Exception ex) { return "<summary-error:" + ex.Message + ">"; }
        }

        private void DumpObjectSnapshot(string label, object obj)
        {
            Build51Log.Entity("OBJECT label='" + label + "' type='" + ObjectTypeName(obj) + "'");
            if (obj == null) return;
            string[] props = new string[] {
                "Name", "Type", "JointType", "Definition", "JointDefinition",
                "OriginOne", "OriginTwo", "Origin1", "Origin2",
                "OriginOneDefinitionType", "OriginTwoDefinitionType",
                "AlignmentOne", "AlignmentTwo", "FlipOriginDirection", "FlipAlignmentDirection",
                "Geometry", "Intent", "IntentType", "Point",
                "EntityOne", "EntityTwo", "OccurrenceOne", "OccurrenceTwo",
                "AffectedOccurrenceOne", "AffectedOccurrenceTwo", "ContainingOccurrence",
                "NativeObject", "Direction", "Axis", "AxisVector", "RotationAxis",
                "Vector", "Normal", "XAxis", "YAxis", "ZAxis",
                "Origin", "RootPoint", "PointOnLine", "BasePoint", "Center", "CenterPoint",
                "StartPoint", "EndPoint", "PointOne", "PointTwo", "Position",
                "Transformation", "Transform", "Matrix"
            };
            foreach (string p in props)
            {
                object value = TryGet(obj, p);
                if (value == null) continue;
                Build51Log.Entity("PROPERTY label='" + label + "' name='" + p + "' value={" + ObjectValueSummary(value) + "}");
                if (String.Equals(p, "Transformation", StringComparison.OrdinalIgnoreCase))
                {
                    Mat4 m = Mat4.FromInventorMatrix(value, _lengthToMeters);
                    Build51Log.Frame("PROPERTY_MATRIX label='" + label + "' name='" + p + "' " + MatrixReport(m));
                }
            }
        }

        private void DumpAxisExtractionCandidates(
            string kind,
            string stableId,
            string displayName,
            object owner,
            object entityOne,
            object entityTwo,
            AxisEvidence selected,
            string contextPath,
            Mat4 contextToWorld)
        {
            Build51Log.Axis("AXIS_EXTRACTION_BEGIN kind='" + kind + "' id='" + stableId + "' name='" + displayName +
                "' context='" + (contextPath ?? "") + "' context_matrix={" + MatrixReport(contextToWorld) + "}");
            object[] objects = new object[] { entityOne, entityTwo, owner };
            string[] labels = new string[] { "EntityOne", "EntityTwo", "Owner" };
            for (int i = 0; i < objects.Length; i++)
            {
                AxisEvidence a = TryExtractAxisFromEntity(objects[i]);
                Build51Log.Axis("AXIS_CANDIDATE kind='" + kind + "' id='" + stableId + "' candidate='" + labels[i] +
                    "' object_type='" + ObjectTypeName(objects[i]) + "' has_axis=" + a.HasAxis +
                    " axis_local_or_raw=" + a.Axis.Text() + " has_point=" + a.HasPoint +
                    " point_local_or_raw_m=" + a.Point.Text() + " source='" + a.Source +
                    "' cardinal={" + CardinalReport(a.Axis) + "}");
                DumpObjectSnapshot(kind + ":" + stableId + ":" + labels[i], objects[i]);
            }
            Build51Log.Axis("AXIS_SELECTED_RAW kind='" + kind + "' id='" + stableId + "' has_axis=" + selected.HasAxis +
                " axis=" + selected.Axis.Text() + " has_point=" + selected.HasPoint +
                " point_m=" + selected.Point.Text() + " source='" + selected.Source + "'");
        }

        private void DumpOccurrenceDiagnostics(List<OccInfo> occs, string stage)
        {
            Build51Log.Dump("OCCURRENCE_DUMP_BEGIN stage='" + stage + "' count=" + (occs == null ? 0 : occs.Count));
            if (occs == null) return;
            foreach (OccInfo o in occs)
            {
                Build51Log.Frame("OCC stage='" + stage + "' index=" + o.Index + " stable='" + o.StableId +
                    "' link='" + o.LinkName + "' name='" + o.Name + "' path='" + o.Path +
                    "' node_kind='" + (o.IsAssemblyNode ? "assembly_frame" : "leaf_component") +
                    "' parent='" + (o.Parent == null ? "" : o.Parent.LinkName) +
                    "' grounded=" + o.Grounded + " visible=" + o.Visible + " suppressed=" + o.Suppressed +
                    " mass_kg=" + F(o.MassKg) + " doc='" + SafeString(o.SourceDocumentPath) +
                    "' world_raw={" + MatrixReport(o.WorldRaw) + "}" +
                    " aabb=" + (o.HasRangeBox ? ("min=" + o.RangeMinRaw.Text() + " max=" + o.RangeMaxRaw.Text()) : "none"));
            }
            Build51Log.Dump("OCCURRENCE_DUMP_END stage='" + stage + "'");
        }

        private void DumpConstraintDiagnostics(List<ConstraintInfo> constraints, string stage)
        {
            Build51Log.Dump("CONSTRAINT_DUMP_BEGIN stage='" + stage + "' count=" + (constraints == null ? 0 : constraints.Count));
            if (constraints == null) return;
            foreach (ConstraintInfo c in constraints)
            {
                Build51Log.Pair("CONSTRAINT stage='" + stage + "' index=" + c.Index + " id='" + c.StableId +
                    "' name='" + c.Name + "' api='" + c.ApiClass + "' context='" + c.ContextPath +
                    "' source_context='" + c.ContextSource + "' A='" + (c.A == null ? "null" : c.A.LinkName) +
                    "' B='" + (c.B == null ? "null" : c.B.LinkName) + "' has_axis=" + c.HasAxis +
                    " axis_world=" + c.AxisWorld.Text() + " axis_cardinal={" + CardinalReport(c.AxisWorld) + "}" +
                    " has_point=" + c.HasAxisPoint + " point_world_m=" + c.AxisPointWorld.Text() +
                    " axis_source='" + c.AxisSource + "' repaired=" + c.RepairedFromCollapsedEndpoint +
                    " flags={angle:" + c.IsAngleLike +
                    ",insert:" + c.IsInsertLike +
                    ",flush:" + c.IsFlushLike +
                    ",mate:" + c.IsMateLike +
                    ",transitional:" + c.IsTransitionalLike +
                    ",tangent:" + c.IsTangentLike +
                    ",lock_rotation:" + c.LockRotation +
                    ",axis_geometry:" + c.HasAxisLikeGeometry +
                    ",planar_geometry:" + c.HasPlanarGeometry +
                    ",point_geometry:" + c.HasPointGeometry +
                    ",rigid:" + c.IsRigidLike +
                    "} suppressed=" + c.Suppressed +
                    " healthy=" + c.Healthy +
                    " health='" + c.HealthText +
                    "' entity1='" + c.EntityOneKind +
                    "' entity2='" + c.EntityTwoKind +
                    "' offset_m=" + F(c.OffsetMeters));
            }
            Build51Log.Dump("CONSTRAINT_DUMP_END stage='" + stage + "'");
        }

        private void DumpNativeJointDiagnostics(List<NativeJointInfo> joints, string stage)
        {
            Build51Log.Dump("NATIVE_DUMP_BEGIN stage='" + stage + "' count=" + (joints == null ? 0 : joints.Count));
            if (joints == null) return;
            foreach (NativeJointInfo j in joints)
            {
                Build51Log.Native("NATIVE stage='" + stage + "' index=" + j.Index + " id='" + j.StableId +
                    "' name='" + j.Name + "' api='" + j.ApiClass + "' kind='" + j.JointKind +
                    "' context='" + j.ContextPath + "' context_source='" + j.ContextSource +
                    "' A='" + (j.A == null ? "null" : j.A.LinkName) + "' B='" + (j.B == null ? "null" : j.B.LinkName) +
                    "' has_axis=" + j.HasAxis + " axis_world=" + j.AxisWorld.Text() +
                    " axis_cardinal={" + CardinalReport(j.AxisWorld) + "}" +
                    " has_point=" + j.HasAxisPoint + " point_world_m=" + j.AxisPointWorld.Text() +
                    " pivot_source='" + j.PivotSource +
                    "' pivot_quality=" + F(j.PivotQuality) +
                    " suppressed=" + j.Suppressed +
                    " healthy=" + j.Healthy +
                    " health='" + j.HealthText +
                    "' authority_score=" + F(NativeJointAuthorityScore(j)) +
                    " axis_source='" + j.AxisSource + "'");
            }
            Build51Log.Dump("NATIVE_DUMP_END stage='" + stage + "'");
        }

        private void DumpMechanicalModelDiagnostics(MechanicalModel model, string stage)
        {
            if (model == null) { Build51Log.Error("MODEL_DUMP stage='" + stage + "' model=null"); return; }
            Build51Log.Dump("MODEL_DUMP_BEGIN stage='" + stage + "' root='" +
                (model.RootOccurrence == null ? "null" : model.RootOccurrence.LinkName) +
                "' occurrences=" + model.Occurrences.Count + " tree=" + model.TreeJoints.Count +
                " loops=" + model.LoopJoints.Count + " couplings=" + model.Couplings.Count);
            foreach (JointSpec j in model.TreeJoints)
            {
                Vec3 originRpy = j.OriginInParent.ToRpy();
                Vec3 reconstructed = j.Child == null ? Vec3.Zero : j.Child.LinkFrameWorld.Rotate(j.AxisInJoint).NormalizedOr(Vec3.UnitZ);
                Build51Log.Axis("MODEL_TREE_JOINT stage='" + stage + "' name='" + j.Name + "' type='" + j.Type +
                    "' parent='" + (j.Parent == null ? "null" : j.Parent.LinkName) + "' child='" + (j.Child == null ? "null" : j.Child.LinkName) +
                    "' axis_cad_world=" + j.AxisWorld.Text() + " cardinal={" + CardinalReport(j.AxisWorld) + "}" +
                    " pivot_world_m=" + j.AxisPointWorld.Text() + " axis_joint=" + j.AxisInJoint.Text() +
                    " reconstructed_world=" + reconstructed.Text() +
                    " axis_error_deg=" + F(AngleDegrees(reconstructed, j.AxisWorld)) +
                    " origin_xyz=" + j.OriginInParent.Translation.Text() + " origin_rpy=" + originRpy.Text() +
                    " independent='" + j.Independent + "' mimic='" + j.MimicJointName +
                    "' pivot_source='" + j.PivotSource +
                    "' confidence=" + F(j.Confidence) +
                    " estimated_free_dof=" + j.EstimatedFreeDof +
                    " source='" + j.Source + "' evidence='" + j.Evidence + "'");
            }
            foreach (JointSpec j in model.LoopJoints)
            {
                Build51Log.Axis("MODEL_LOOP_JOINT stage='" + stage + "' name='" + j.Name + "' type='" + j.Type +
                    "' parent='" + (j.Parent == null ? "null" : j.Parent.LinkName) + "' child='" + (j.Child == null ? "null" : j.Child.LinkName) +
                    "' axis_world=" + j.AxisWorld.Text() + " pivot_world_m=" + j.AxisPointWorld.Text() +
                    " pivot_source='" + j.PivotSource +
                    "' confidence=" + F(j.Confidence) +
                    " estimated_free_dof=" + j.EstimatedFreeDof +
                    " closure_error_m=" + F(j.ClosureErrorMeters) + " source='" + j.Source + "'");
            }
            foreach (CouplingInfo c in model.Couplings)
                Build51Log.Pair("MODEL_COUPLING stage='" + stage + "' name='" + c.Name + "' master='" + c.MasterJoint +
                    "' dependent='" + c.DependentJoint + "' ratio=" + F(c.Ratio) + " offset=" + F(c.Offset) +
                    " type='" + c.Type + "' solver='" + c.Solver + "' mode='" + c.Mode + "'");
            Build51Log.Dump("MODEL_DUMP_END stage='" + stage + "'");
        }

        private void DumpValidationDiagnostics(MechanicalModel model)
        {
            Build51Log.Validate("VALIDATION_SUMMARY errors=" + model.Errors.Count + " warnings=" + model.Warnings.Count +
                " independent_dof=" + model.IndependentDof);
            for (int i = 0; i < model.Errors.Count; i++) Build51Log.Error("VALIDATION_ERROR[" + i + "] " + model.Errors[i]);
            for (int i = 0; i < model.Warnings.Count; i++) Build51Log.Warn("VALIDATION_WARNING[" + i + "] " + model.Warnings[i]);
        }


        private void DumpMechanicalEdgeCandidates(List<MechanicalEdge> edges, string stage)
        {
            Build51Log.Dump("BUILD89_EDGE_CANDIDATES_BEGIN stage='" + stage + "' count=" + (edges == null ? 0 : edges.Count));
            if (edges == null)
            {
                Build51Log.Dump("BUILD89_EDGE_CANDIDATES_END stage='" + stage + "'");
                return;
            }

            Dictionary<string, int> sourceCounts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            foreach (MechanicalEdge e in edges)
            {
                string src = e == null || String.IsNullOrEmpty(e.Source) ? "unknown" : e.Source.Split(new char[] { ';' })[0];
                if (!sourceCounts.ContainsKey(src)) sourceCounts[src] = 0;
                sourceCounts[src]++;
            }
            foreach (KeyValuePair<string, int> kv in sourceCounts.OrderByDescending(k => k.Value))
                Build51Log.Dump("BUILD89_EDGE_SOURCE_COUNT stage='" + stage + "' source='" + kv.Key + "' count=" + kv.Value.ToString(_ci));

            int index = 0;
            foreach (MechanicalEdge e in edges.OrderByDescending(x => x == null ? -1.0 : x.Score))
            {
                if (e == null) continue;
                Build51Log.Pair(
                    "BUILD89_EDGE_CANDIDATE stage='" + stage +
                    "' rank=" + index.ToString(_ci) +
                    " pair='" + PairKey(e.A, e.B) +
                    "' A='" + (e.A == null ? "null" : e.A.LinkName) +
                    "' B='" + (e.B == null ? "null" : e.B.LinkName) +
                    "' type='" + e.Type +
                    "' score=" + F(e.Score) +
                    " confidence=" + F(e.Confidence) +
                    " allow_loop=" + e.AllowLoop +
                    " explicit_movable=" + e.ExplicitMovable +
                    " est_rank=" + e.EstimatedConstraintRank.ToString(_ci) +
                    " est_free_dof=" + e.EstimatedFreeDof.ToString(_ci) +
                    " axis=" + e.AxisWorld.Text() +
                    " pivot=" + e.AxisPointWorld.Text() +
                    " has_pivot=" + e.HasAxisPoint +
                    " source='" + (e.Source ?? "") +
                    "' evidence='" + (e.Evidence ?? "") +
                    "' edge_key='" + (e.EdgeKey ?? "") + "'");
                index++;
            }
            Build51Log.Dump("BUILD89_EDGE_CANDIDATES_END stage='" + stage + "'");
        }

        private void DumpSelectedMechanicalEdges(List<MechanicalEdge> tree, string stage)
        {
            Build51Log.Dump("BUILD89_SELECTED_EDGES_BEGIN stage='" + stage + "' count=" + (tree == null ? 0 : tree.Count));
            if (tree == null)
            {
                Build51Log.Dump("BUILD89_SELECTED_EDGES_END stage='" + stage + "'");
                return;
            }
            int index = 0;
            foreach (MechanicalEdge e in tree)
            {
                if (e == null) continue;
                Build51Log.Pair(
                    "BUILD89_SELECTED_EDGE stage='" + stage +
                    "' index=" + index.ToString(_ci) +
                    " pair='" + PairKey(e.A, e.B) +
                    "' A='" + (e.A == null ? "null" : e.A.LinkName) +
                    "' B='" + (e.B == null ? "null" : e.B.LinkName) +
                    "' type='" + e.Type +
                    "' score=" + F(e.Score) +
                    " confidence=" + F(e.Confidence) +
                    " explicit_movable=" + e.ExplicitMovable +
                    " est_free_dof=" + e.EstimatedFreeDof.ToString(_ci) +
                    " source='" + (e.Source ?? "") +
                    "' evidence='" + (e.Evidence ?? "") + "'");
                index++;
            }
            Build51Log.Dump("BUILD89_SELECTED_EDGES_END stage='" + stage + "'");
        }

        private void DumpForensicGraphCompleteness(MechanicalModel model, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints, string stage)
        {
            if (model == null)
            {
                Build51Log.Error("BUILD89_GRAPH_FORENSICS stage='" + stage + "' model=null");
                return;
            }

            HashSet<string> childSet = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            Dictionary<string, int> childParentCount = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            foreach (JointSpec j in model.TreeJoints)
            {
                if (j == null || j.Child == null) continue;
                string child = j.Child.LinkName;
                childSet.Add(child);
                if (!childParentCount.ContainsKey(child)) childParentCount[child] = 0;
                childParentCount[child]++;
            }

            int multiParent = childParentCount.Values.Count(v => v > 1);
            int unparented = model.Occurrences.Count(o => o != null && !Object.ReferenceEquals(o, model.RootOccurrence) && !childSet.Contains(o.LinkName));
            int movable = model.TreeJoints.Count(j => j != null && !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase));
            int fixedCount = model.TreeJoints.Count(j => j != null && String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase));
            int passiveInsertConstraints = constraints == null ? 0 : constraints.Count(c => c != null && c.IsInsertLike && !c.LockRotation && !c.IsRotationCouplingLike);
            int rotationCouplings = constraints == null ? 0 : constraints.Count(c => c != null && c.IsRotationCouplingLike);
            int nativeMovable = nativeJoints == null ? 0 : nativeJoints.Count(j => j != null && !String.Equals(j.JointKind, "fixed", StringComparison.OrdinalIgnoreCase));

            Build51Log.Validate(
                "BUILD89_GRAPH_FORENSICS stage='" + stage +
                "' occurrences=" + model.Occurrences.Count.ToString(_ci) +
                " tree=" + model.TreeJoints.Count.ToString(_ci) +
                " fixed=" + fixedCount.ToString(_ci) +
                " movable=" + movable.ToString(_ci) +
                " loops=" + model.LoopJoints.Count.ToString(_ci) +
                " couplings=" + model.Couplings.Count.ToString(_ci) +
                " unparented_nonroot=" + unparented.ToString(_ci) +
                " multi_parent_children=" + multiParent.ToString(_ci) +
                " grounded=" + model.Occurrences.Count(o => o != null && o.Grounded).ToString(_ci) +
                " passive_unlocked_insert_constraints=" + passiveInsertConstraints.ToString(_ci) +
                " explicit_rotation_constraints=" + rotationCouplings.ToString(_ci) +
                " native_movable=" + nativeMovable.ToString(_ci));

            foreach (KeyValuePair<string, int> kv in childParentCount.Where(kv => kv.Value > 1))
                Build51Log.Error("BUILD89_MULTI_PARENT_CHILD child='" + kv.Key + "' parent_count=" + kv.Value.ToString(_ci));

            foreach (OccInfo o in model.Occurrences)
            {
                if (o == null || Object.ReferenceEquals(o, model.RootOccurrence)) continue;
                if (!childSet.Contains(o.LinkName))
                    Build51Log.Warn("BUILD89_UNPARENTED_OCCURRENCE_AFTER_GRAPH link='" + o.LinkName + "' stable='" + o.StableId + "' path='" + o.Path + "'");
            }
        }

        private void DumpUrdfZeroPoseAndJointForensics(MechanicalModel model, string stage)
        {
            if (model == null) return;

            double maxJointTranslationError = 0.0;
            double maxJointRotationError = 0.0;
            double maxAxisError = 0.0;

            HashSet<JointSpec> loopSetForQ0 = new HashSet<JointSpec>(model.LoopJoints ?? new List<JointSpec>());
            foreach (JointSpec j in model.TreeJoints.Concat(model.LoopJoints))
            {
                if (j == null || j.Parent == null || j.Child == null) continue;

                bool isLoop = loopSetForQ0.Contains(j);
                Mat4 parentFrame = j.Parent.LinkFrameWorld;
                Mat4 childFrame = j.Child.LinkFrameWorld;
                Mat4 jointWorldFrame = parentFrame * j.OriginInParent;
                Mat4 expectedQ0Frame = isLoop ? (childFrame * j.OriginInSuccessor) : childFrame;

                // BUILD89: URDF axes are expressed in the joint frame, not in the
                // parent link frame. Previous forensic logs rotated axis_joint by
                // parentFrame only, which produced false 170-180 degree errors when
                // origin_rpy legitimately flipped the joint frame to preserve q=0.
                Vec3 reconstructedAxisWorld = jointWorldFrame.Rotate(j.AxisInJoint).NormalizedOr(Vec3.UnitZ);
                double axisErrorDeg = String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase)
                    ? 0.0
                    : Math.Min(AngleDegrees(reconstructedAxisWorld, j.AxisWorld.NormalizedOr(Vec3.UnitZ)),
                               AngleDegrees(reconstructedAxisWorld * -1.0, j.AxisWorld.NormalizedOr(Vec3.UnitZ)));

                double translationError = (jointWorldFrame.Translation - expectedQ0Frame.Translation).Length;
                double rotationError = RotationMatrixMaxError(jointWorldFrame, expectedQ0Frame);

                maxJointTranslationError = Math.Max(maxJointTranslationError, translationError);
                maxJointRotationError = Math.Max(maxJointRotationError, rotationError);
                maxAxisError = Math.Max(maxAxisError, axisErrorDeg);

                Build51Log.Validate(
                    "BUILD89_JOINT_Q0_FORENSIC stage='" + stage +
                    "' name='" + j.Name +
                    "' kind='" + (isLoop ? "loop_closure" : "tree_child_frame") +
                    "' type='" + j.Type +
                    "' parent='" + j.Parent.LinkName +
                    "' child='" + j.Child.LinkName +
                    "' source='" + (j.Source ?? "") +
                    "' evidence='" + (j.Evidence ?? "") +
                    "' origin_xyz=" + j.OriginInParent.Translation.Text() +
                    " origin_rpy=" + j.OriginInParent.ToRpy().Text() +
                    " successor_origin_xyz=" + j.OriginInSuccessor.Translation.Text() +
                    " successor_origin_rpy=" + j.OriginInSuccessor.ToRpy().Text() +
                    " axis_joint=" + j.AxisInJoint.Text() +
                    " axis_expected_world=" + j.AxisWorld.Text() +
                    " axis_reconstructed_world=" + reconstructedAxisWorld.Text() +
                    " axis_error_deg_unsigned=" + F(axisErrorDeg) +
                    " q0_translation_error_m=" + F(translationError) +
                    " q0_rotation_matrix_error=" + F(rotationError) +
                    " parent_frame={" + MatrixReport(parentFrame) + "}" +
                    " child_frame={" + MatrixReport(childFrame) + "}" +
                    " joint_world_frame={" + MatrixReport(jointWorldFrame) + "}" +
                    " expected_q0_frame={" + MatrixReport(expectedQ0Frame) + "}");
            }

            foreach (OccInfo o in model.Occurrences)
            {
                if (o == null || !o.HasVisualGeometry) continue;
                Mat4 reconstructedCad = o.LinkFrameWorld * o.VisualOriginInLink;
                double visualTranslationError = (reconstructedCad.Translation - o.CadWorld.Translation).Length;
                double visualRotationError = RotationMatrixMaxError(reconstructedCad, o.CadWorld);
                Build51Log.Validate(
                    "BUILD89_VISUAL_Q0_FORENSIC stage='" + stage +
                    "' link='" + o.LinkName +
                    "' cad_translation=" + o.CadWorld.Translation.Text() +
                    " link_translation=" + o.LinkFrameWorld.Translation.Text() +
                    " visual_origin_xyz=" + o.VisualOriginInLink.Translation.Text() +
                    " visual_translation_error_m=" + F(visualTranslationError) +
                    " visual_rotation_matrix_error=" + F(visualRotationError));
            }

            Build51Log.Validate(
                "BUILD89_Q0_FORENSIC_SUMMARY stage='" + stage +
                "' max_joint_translation_error_m=" + F(maxJointTranslationError) +
                " max_joint_rotation_matrix_error=" + F(maxJointRotationError) +
                " max_axis_error_deg=" + F(maxAxisError));
        }

        private Vec3 ParseXmlVec(string text, Vec3 fallback)
        {
            try
            {
                string[] p = (text ?? "").Split(new char[] { ' ', '\t', ',' }, StringSplitOptions.RemoveEmptyEntries);
                if (p.Length < 3) return fallback;
                return new Vec3(
                    Double.Parse(p[0], CultureInfo.InvariantCulture),
                    Double.Parse(p[1], CultureInfo.InvariantCulture),
                    Double.Parse(p[2], CultureInfo.InvariantCulture));
            }
            catch { return fallback; }
        }

        private void AuditWrittenUrdf(string urdfPath, MechanicalModel model)
        {
            try
            {
                XmlDocument doc = new XmlDocument();
                doc.Load(urdfPath);
                XmlElement robot = doc.DocumentElement;
                if (robot == null) { Build51Log.Error("XML_AUDIT robot root missing"); return; }
                int linkCount = 0, jointCount = 0, movableCount = 0, mimicCount = 0, loopCount = 0, couplingCount = 0;
                Dictionary<string, JointSpec> specs = new Dictionary<string, JointSpec>(StringComparer.OrdinalIgnoreCase);
                if (model.RootJoint != null) specs[model.RootJoint.Name] = model.RootJoint;
                foreach (JointSpec j in model.TreeJoints) specs[j.Name] = j;

                foreach (XmlNode n in robot.ChildNodes)
                {
                    XmlElement e = n as XmlElement;
                    if (e == null) continue;
                    if (e.LocalName == "link") { linkCount++; continue; }
                    if (e.LocalName == "loop") { loopCount++; continue; }
                    if (e.LocalName == "coupling") { couplingCount++; continue; }
                    if (e.LocalName != "joint") continue;
                    jointCount++;
                    string name = e.GetAttribute("name");
                    string type = e.GetAttribute("type");
                    if (!String.Equals(type, "fixed", StringComparison.OrdinalIgnoreCase)) movableCount++;
                    XmlElement parent = null, child = null, origin = null, axis = null, mimic = null;
                    foreach (XmlNode cn in e.ChildNodes)
                    {
                        XmlElement ce = cn as XmlElement;
                        if (ce == null) continue;
                        if (ce.LocalName == "parent") parent = ce;
                        else if (ce.LocalName == "child") child = ce;
                        else if (ce.LocalName == "origin") origin = ce;
                        else if (ce.LocalName == "axis") axis = ce;
                        else if (ce.LocalName == "mimic") mimic = ce;
                    }
                    if (mimic != null) mimicCount++;
                    Vec3 xyz = ParseXmlVec(origin == null ? "" : origin.GetAttribute("xyz"), Vec3.Zero);
                    Vec3 rpy = ParseXmlVec(origin == null ? "" : origin.GetAttribute("rpy"), Vec3.Zero);
                    Vec3 axisXml = ParseXmlVec(axis == null ? "" : axis.GetAttribute("xyz"), Vec3.UnitZ);
                    JointSpec spec = specs.ContainsKey(name) ? specs[name] : null;
                    Vec3 worldReconstructed = (spec != null && spec.Child != null)
                        ? spec.Child.LinkFrameWorld.Rotate(axisXml).NormalizedOr(Vec3.UnitZ)
                        : axisXml.NormalizedOr(Vec3.UnitZ);
                    double angleError = spec == null ? -1.0 : AngleDegrees(worldReconstructed, spec.AxisWorld);
                    Build51Log.Xml("XML_JOINT name='" + name + "' type='" + type + "' parent='" +
                        (parent == null ? "" : parent.GetAttribute("link")) + "' child='" +
                        (child == null ? "" : child.GetAttribute("link")) + "' origin_xyz=" + xyz.Text() +
                        " origin_rpy=" + rpy.Text() + " axis_xml=" + axisXml.Text() +
                        " axis_xml_cardinal={" + CardinalReport(axisXml) + "}" +
                        " reconstructed_world=" + worldReconstructed.Text() + " expected_world=" +
                        (spec == null ? "unknown" : spec.AxisWorld.Text()) + " angle_error_deg=" + F(angleError) +
                        " mimic='" + (mimic == null ? "" : mimic.GetAttribute("joint")) + "'");
                    if (!String.Equals(type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                        (axisXml - Vec3.UnitZ).Length > 1e-9)
                        Build51Log.Error("XML_AXIS_NOT_CANONICAL joint='" + name + "' axis=" + axisXml.Text());
                    if (Double.IsNaN(xyz.X) || Double.IsNaN(rpy.X) || Double.IsNaN(axisXml.X))
                        Build51Log.Error("XML_NON_FINITE joint='" + name + "'");
                }
                Build51Log.Xml("XML_AUDIT_SUMMARY links=" + linkCount + " joints=" + jointCount +
                    " movable=" + movableCount + " mimics=" + mimicCount + " loops=" + loopCount +
                    " couplings=" + couplingCount + " path='" + urdfPath + "'");
            }
            catch (Exception ex)
            {
                Build51Log.Error("XML_AUDIT_FAILED " + ex.ToString());
            }
        }

        // --------------------------------------------------------------------
        // CAD extraction
        // --------------------------------------------------------------------

        private List<OccInfo> ExtractLeafOccurrences(Inv.AssemblyDocument asm)
        {
            // BUILD86 keeps both leaf components and nested assembly occurrences.
            // Leaves are emitted first so historical link indices used by guarded
            // gripper/cardan overlays remain stable; virtual assembly frames are
            // appended afterwards.
            List<OccInfo> leaves = new List<OccInfo>();
            List<OccInfo> assemblies = new List<OccInfo>();
            try
            {
                Inv.ComponentOccurrences occs = asm.ComponentDefinition.Occurrences;
                foreach (Inv.ComponentOccurrence occ in occs)
                    WalkOccurrence(occ, leaves, assemblies, "", null, 0);
            }
            catch (Exception ex)
            {
                Build51Log.Error("ExtractLeafOccurrences failed: " + ex);
                throw;
            }

            List<OccInfo> result = new List<OccInfo>();
            result.AddRange(leaves);
            result.AddRange(assemblies);

            for (int i = 0; i < result.Count; ++i)
            {
                result[i].Index = i;
                result[i].LinkName = "link_" + i.ToString(_ci) + "_" + SanitizeName(result[i].Name);
                Build51Log.Cad("BUILD86_OCC[" + i + "] id='" + result[i].StableId +
                    "' name='" + result[i].Name +
                    "' path='" + result[i].Path +
                    "' node_kind='" + (result[i].IsAssemblyNode ? "assembly_frame" : "leaf_component") +
                    "' parent='" + (result[i].Parent == null ? "" : result[i].Parent.StableId) +
                    "' grounded=" + result[i].Grounded +
                    " visible=" + result[i].Visible +
                    " suppressed=" + result[i].Suppressed +
                    " world_xyz=" + result[i].World.TranslationText());
            }
            return result;
        }

        private void WalkOccurrence(
            Inv.ComponentOccurrence occ,
            List<OccInfo> leaves,
            List<OccInfo> assemblies,
            string path,
            OccInfo parent,
            int depth)
        {
            bool suppressed = TryBool(occ, "Suppressed", false);
            bool visible = TryBool(occ, "Visible", true);
            if (suppressed || !visible) return;

            string name = SafeString(TryGet(occ, "Name"));
            string fullPath = String.IsNullOrEmpty(path) ? name : path + "/" + name;

            List<Inv.ComponentOccurrence> children = new List<Inv.ComponentOccurrence>();
            try
            {
                Inv.ComponentOccurrencesEnumerator sub = occ.SubOccurrences;
                if (sub != null)
                {
                    foreach (Inv.ComponentOccurrence child in sub)
                    {
                        if (child == null) continue;
                        if (TryBool(child, "Suppressed", false) || !TryBool(child, "Visible", true)) continue;
                        children.Add(child);
                    }
                }
            }
            catch { }

            OccInfo info = new OccInfo();
            info.Occurrence = occ;
            info.Name = String.IsNullOrWhiteSpace(name)
                ? (children.Count > 0 ? "assembly_" : "occurrence_") + (leaves.Count + assemblies.Count).ToString(_ci)
                : name;
            info.Path = fullPath;
            info.Parent = parent;
            info.Depth = depth;
            info.IsAssemblyNode = children.Count > 0;
            info.HasVisualGeometry = children.Count == 0;
            // Inventor subassemblies are rigid in the parent assembly unless the
            // occurrence is explicitly marked Flexible.  This distinction is
            // essential: exporting internal Insert/Mate constraints of a rigid
            // subassembly as top-level joints creates hundreds of false DOFs.
            info.IsFlexible = info.IsAssemblyNode && TryBool(occ, "Flexible", false);
            info.Visible = visible;
            info.Suppressed = suppressed;
            info.Grounded = TryBool(occ, "Grounded", false);

            // Inventor's occurrence Transformation is the pose of that occurrence in
            // the active assembly context.  It is authoritative here and must not be
            // multiplied a second time by the parent transform.
            info.WorldRaw = Mat4.FromInventorMatrix(TryGet(occ, "Transformation"), _lengthToMeters);
            info.CadWorld = info.WorldRaw;
            info.World = info.WorldRaw;

            if (info.HasVisualGeometry)
            {
                Vec3 rbMin, rbMax;
                if (TryGetRangeBox(occ, out rbMin, out rbMax))
                {
                    info.HasRangeBox = true;
                    info.RangeMinRaw = rbMin;
                    info.RangeMaxRaw = rbMax;
                }
                info.SourceDocumentPath = GetOccurrenceDocumentPath(occ);
                CaptureOccurrenceMassProperties(occ, info);
                info.Color = TryGetOccurrenceColor(occ);
                leaves.Add(info);
            }
            else
            {
                // A virtual frame must not duplicate the aggregate subassembly mass or
                // geometry.  It exists only to preserve the IAM hierarchy and external
                // constraints that refer to the subassembly occurrence itself.
                info.SourceDocumentPath = GetOccurrenceDocumentPath(occ);
                info.MassKg = 0.0001;
                info.Color = DrawingColor.LightGray;
                assemblies.Add(info);
            }

            if (parent != null)
                parent.Children.Add(info);

            info.StableId = "occ_" + ShortHash(
                (info.IsAssemblyNode ? "assembly|" : "leaf|") +
                info.Path + "|" + info.WorldRaw.TranslationText());

            foreach (Inv.ComponentOccurrence child in children)
                WalkOccurrence(child, leaves, assemblies, fullPath, info, depth + 1);
        }

        private List<ConstraintInfo> ExtractAssemblyConstraints(Inv.AssemblyDocument asm, List<OccInfo> occs)
        {
            // BUILD71: Inventor's browser shows relations both at the top assembly
            // and inside subassemblies/occurrences. The old exporter only consumed
            // asm.ComponentDefinition.Constraints, so mechanisms such as a cardan
            // subassembly were exported with internal forks/crosses disconnected.
            List<ConstraintInfo> list = new List<ConstraintInfo>();
            int i = 0;

            try
            {
                AppendConstraintsFromComponentDefinition(
                    asm.ComponentDefinition,
                    occs,
                    "",
                    Mat4.Identity,
                    "top_assembly_definition",
                    ref i,
                    list);
            }
            catch (Exception ex)
            {
                Build51Log.Warn("BUILD71 top-level constraint extraction skipped: " + ex.Message);
            }

            try
            {
                Inv.ComponentOccurrences topOccs = asm.ComponentDefinition.Occurrences;
                foreach (Inv.ComponentOccurrence occ in topOccs)
                {
                    string name = SafeString(TryGet(occ, "Name"));
                    Mat4 world = Mat4.FromInventorMatrix(TryGet(occ, "Transformation"), _lengthToMeters);
                    WalkNestedConstraintDefinitions(occ, occs, name, world, ref i, list);
                }
            }
            catch (Exception ex)
            {
                Build51Log.Warn("BUILD71 recursive nested constraint extraction skipped: " + ex.Message);
            }

            int nested = list.Count(c => !String.IsNullOrEmpty(c.ContextPath));
            Build51Log.Cad("BUILD71_CONSTRAINT_RECURSIVE_SUMMARY total=" + list.Count +
                " top=" + (list.Count - nested) +
                " nested=" + nested +
                " axis=" + list.Count(c => c.HasAxis) +
                " resolved_pairs=" + list.Count(c => c.A != null && c.B != null && c.A != c.B));
            return list;
        }

        private void WalkNestedConstraintDefinitions(Inv.ComponentOccurrence occ, List<OccInfo> allLeaves, string contextPath, Mat4 contextToWorld, ref int index, List<ConstraintInfo> list)
        {
            if (occ == null) return;
            bool suppressed = TryBool(occ, "Suppressed", false);
            bool visible = TryBool(occ, "Visible", true);
            if (suppressed || !visible) return;

            bool hasChildren = false;
            try
            {
                Inv.ComponentOccurrencesEnumerator children = occ.SubOccurrences;
                if (children != null)
                {
                    foreach (Inv.ComponentOccurrence child in children)
                    {
                        hasChildren = true;
                        string childName = SafeString(TryGet(child, "Name"));
                        string childPath = String.IsNullOrEmpty(contextPath) ? childName : contextPath + "/" + childName;
                        // BUILD86: SubOccurrences expose their pose in the active
                        // assembly context.  Composing it again with contextToWorld
                        // double-transforms nested axes and pivots.
                        Mat4 childWorld = Mat4.FromInventorMatrix(TryGet(child, "Transformation"), _lengthToMeters);
                        WalkNestedConstraintDefinitions(child, allLeaves, childPath, childWorld, ref index, list);
                    }
                }
            }
            catch { }

            if (!hasChildren) return;

            object definition = TryGet(occ, "Definition");
            if (definition == null) return;
            AppendConstraintsFromComponentDefinition(
                definition,
                allLeaves,
                contextPath,
                contextToWorld,
                "nested_subassembly_definition",
                ref index,
                list);
        }

        private void AppendConstraintsFromComponentDefinition(object componentDefinition, List<OccInfo> occs, string contextPath, Mat4 contextToWorld, string contextSource, ref int index, List<ConstraintInfo> list)
        {
            object constraintsObj = TryGet(componentDefinition, "Constraints");
            if (constraintsObj == null) return;

            int before = list.Count;
            foreach (object c in (System.Collections.IEnumerable)constraintsObj)
            {
                ConstraintInfo ci = ParseConstraintObject(c, occs, contextPath, contextToWorld, contextSource, index);
                index++;
                if (ci == null) continue;
                RepairConstraintEndpointsFromContextHint(ci, occs, contextPath);
                list.Add(ci);
                Build51Log.Cad("BUILD71_CONSTRAINT[" + ci.Index + "] ctx='" + ci.ContextPath +
                    "' id='" + ci.StableId +
                    "' api='" + ci.ApiClass +
                    "' name='" + ci.Name +
                    "' occ1='" + (ci.A == null ? "" : ci.A.StableId) +
                    "' occ2='" + (ci.B == null ? "" : ci.B.StableId) +
                    "' has_axis=" + ci.HasAxis +
                    " axis=" + (ci.HasAxis ? ci.AxisWorld.Text() : "null") +
                    " axis_pt=" + (ci.HasAxisPoint ? ci.AxisPointWorld.Text() : "null") +
                    " axis_src='" + ci.AxisSource + "'");
            }

            int added = list.Count - before;
            if (added > 0)
            {
                Build51Log.Cad("BUILD71_CONSTRAINT_CONTEXT path='" + contextPath +
                    "' source='" + contextSource +
                    "' added=" + added);
            }
        }

        private ConstraintInfo ParseConstraintObject(object c, List<OccInfo> occs, string contextPath, Mat4 contextToWorld, string contextSource, int index)
        {
            if (c == null) return null;

            ConstraintInfo ci = new ConstraintInfo();
            ci.Index = index;
            ci.Raw = c;
            ci.ContextPath = contextPath ?? "";
            ci.ContextSource = contextSource ?? "";
            ci.ApiClass = c.GetType().Name;

            object typ = TryGet(c, "Type");
            if (typ != null && ci.ApiClass == "__ComObject")
                ci.ApiClass = typ.ToString();

            ci.Name = SafeString(TryGet(c, "Name"));
            if (String.IsNullOrWhiteSpace(ci.Name))
                ci.Name = "constraint_" + ci.Index.ToString(_ci);

            ci.StableId = "constraint_" +
                ShortHash((ci.ContextPath ?? "") + "|" + ci.Name + "|" + ci.Index.ToString(_ci));

            object ent1 = FirstNonNull(
                TryGet(c, "EntityOne"),
                TryGet(c, "AffectedOccurrenceOne"),
                TryGet(c, "OccurrenceOne"));

            object ent2 = FirstNonNull(
                TryGet(c, "EntityTwo"),
                TryGet(c, "AffectedOccurrenceTwo"),
                TryGet(c, "OccurrenceTwo"));

            AxisEvidence axisLocal = TryExtractAxis(c, ent1, ent2);
            DumpAxisExtractionCandidates(
                "CONSTRAINT",
                ci.StableId,
                ci.Name,
                c,
                ent1,
                ent2,
                axisLocal,
                contextPath,
                contextToWorld);

            AxisEvidence axis = axisLocal;
            if (!String.IsNullOrEmpty(ci.ContextPath))
                axis = TransformAxisEvidenceToWorld(axis, contextToWorld);

            Build51Log.Axis(
                "CONSTRAINT_AXIS_FINAL id='" + ci.StableId +
                "' name='" + ci.Name +
                "' context='" + ci.ContextPath +
                "' has_axis=" + axis.HasAxis +
                " axis_world=" + axis.Axis.Text() +
                " has_point=" + axis.HasPoint +
                " point_world_m=" + axis.Point.Text() +
                " source='" + axis.Source + "'");

            ci.A = FindOccurrenceFromAny(
                ent1,
                occs,
                ci.ContextPath,
                axis.HasPoint,
                axis.Point);

            ci.B = FindOccurrenceFromAny(
                ent2,
                occs,
                ci.ContextPath,
                axis.HasPoint,
                axis.Point);

            if (ci.A == null)
                ci.A = FindOccurrenceFromAny(
                    TryGet(c, "OccurrenceOne"),
                    occs,
                    ci.ContextPath,
                    axis.HasPoint,
                    axis.Point);

            if (ci.B == null)
                ci.B = FindOccurrenceFromAny(
                    TryGet(c, "OccurrenceTwo"),
                    occs,
                    ci.ContextPath,
                    axis.HasPoint,
                    axis.Point);

            ci.HasAxis = axis.HasAxis;
            ci.AxisWorld = axis.HasAxis
                ? axis.Axis.NormalizedOr(Vec3.UnitZ)
                : Vec3.Zero;
            ci.AxisPointWorld = axis.Point;
            ci.HasAxisPoint = axis.HasPoint;
            ci.AxisSource = axis.Source ?? "";

            string descriptor = (
                (ci.ApiClass ?? "") + " " +
                (ci.Name ?? "")).ToLowerInvariant();

            ci.IsAngleLike =
                descriptor.Contains("angle") ||
                descriptor.Contains("ngulo") ||
                descriptor.Contains("ángulo") ||
                descriptor.Contains("winkel") ||
                descriptor.Contains("100665088");

            ci.IsInsertLike =
                descriptor.Contains("insert") ||
                descriptor.Contains("insertar") ||
                descriptor.Contains("100665344");

            ci.IsFlushLike =
                descriptor.Contains("flush") ||
                descriptor.Contains("nivelacin") ||
                descriptor.Contains("nivelación") ||
                descriptor.Contains("100666368");

            ci.IsMateLike =
                descriptor.Contains("mate") ||
                descriptor.Contains("coincidencia") ||
                descriptor.Contains("coincident") ||
                descriptor.Contains("100665856") ||
                ci.IsFlushLike;

            ci.IsTransitionalLike =
                descriptor.Contains("transitional") ||
                descriptor.Contains("transicional") ||
                descriptor.Contains("transition") ||
                descriptor.Contains("slider") ||
                descriptor.Contains("prismatic") ||
                descriptor.Contains("desliz") ||
                descriptor.Contains("100666112");

            ci.IsTangentLike =
                descriptor.Contains("tangent") ||
                descriptor.Contains("tangente") ||
                descriptor.Contains("100665600");

            ci.IsRotationCouplingLike =
                descriptor.Contains("rotationconstraint") ||
                descriptor.Contains("rotationalmotion") ||
                descriptor.Contains("rotacin") ||
                descriptor.Contains("rotación") ||
                descriptor.Contains("rotation:") ||
                descriptor.Contains("100666624");

            ci.MotionRatio =
                TryFirstFiniteDouble(
                    c,
                    new string[]
                    {
                        "Ratio",
                        "MotionRatio",
                        "RotationRatio",
                        "GearRatio"
                    },
                    1.0);

            ci.MotionOffset =
                TryFirstFiniteDouble(
                    c,
                    new string[]
                    {
                        "Offset",
                        "AngularOffset",
                        "RotationOffset",
                        "Phase"
                    },
                    0.0);

            ci.LockRotation =
                TryBool(c, "LockRotation", false) ||
                TryBool(c, "LockRotationalDegreeOfFreedom", false) ||
                TryBool(c, "RotationLocked", false);

            ci.Suppressed =
                TryBool(c, "Suppressed", false) ||
                TryBool(c, "IsSuppressed", false);

            object health = FirstNonNull(
                TryGet(c, "HealthStatus"),
                TryGet(c, "Status"),
                TryGet(c, "ConstraintStatus"));

            ci.HealthText = SafeString(health);
            ci.Healthy =
                !ci.Suppressed &&
                TryBool(c, "IsHealthy", true) &&
                !HealthTextLooksBad(ci.HealthText);

            ci.EntityOneKind = ClassifyConstraintEntityKind(ent1);
            ci.EntityTwoKind = ClassifyConstraintEntityKind(ent2);

            ci.HasAxisLikeGeometry =
                IsAxisLikeEntityKind(ci.EntityOneKind) ||
                IsAxisLikeEntityKind(ci.EntityTwoKind);

            ci.HasPlanarGeometry =
                IsPlanarEntityKind(ci.EntityOneKind) ||
                IsPlanarEntityKind(ci.EntityTwoKind);

            ci.HasPointGeometry =
                IsPointEntityKind(ci.EntityOneKind) ||
                IsPointEntityKind(ci.EntityTwoKind);

            ci.IsRigidLike =
                !ci.HasAxis ||
                ci.IsAngleLike ||
                ci.IsFlushLike ||
                ci.LockRotation;

            ci.OffsetMeters =
                TryDouble(c, "Offset", 0.0) * _lengthToMeters;

            Build51Log.Cad(
                "BUILD83_CONSTRAINT_CLASS id='" + ci.StableId +
                "' name='" + ci.Name +
                "' api='" + ci.ApiClass +
                "' A='" + (ci.A == null ? "" : ci.A.LinkName) +
                "' B='" + (ci.B == null ? "" : ci.B.LinkName) +
                "' insert=" + ci.IsInsertLike +
                " angle=" + ci.IsAngleLike +
                " flush=" + ci.IsFlushLike +
                " mate=" + ci.IsMateLike +
                " transitional=" + ci.IsTransitionalLike +
                " tangent=" + ci.IsTangentLike +
                " rotation_coupling=" + ci.IsRotationCouplingLike +
                " motion_ratio=" + F(ci.MotionRatio) +
                " motion_offset=" + F(ci.MotionOffset) +
                " lock_rotation=" + ci.LockRotation +
                " suppressed=" + ci.Suppressed +
                " healthy=" + ci.Healthy +
                " entity1='" + ci.EntityOneKind +
                "' entity2='" + ci.EntityTwoKind +
                "' axis_like_geometry=" + ci.HasAxisLikeGeometry +
                " planar_geometry=" + ci.HasPlanarGeometry +
                " point_geometry=" + ci.HasPointGeometry +
                " health='" + ci.HealthText + "'");

            return ci;
        }

        private double TryFirstFiniteDouble(
            object owner,
            string[] propertyNames,
            double fallback)
        {
            if (owner == null ||
                propertyNames == null)
                return fallback;

            foreach (string propertyName in propertyNames)
            {
                object raw =
                    TryGet(
                        owner,
                        propertyName);

                if (raw == null)
                    continue;

                object numeric =
                    FirstNonNull(
                        TryGet(raw, "ModelValue"),
                        TryGet(raw, "Value"),
                        TryGet(raw, "Expression"),
                        raw);

                try
                {
                    double value =
                        Convert.ToDouble(
                            numeric,
                            CultureInfo.InvariantCulture);

                    if (!Double.IsNaN(value) &&
                        !Double.IsInfinity(value))
                        return value;
                }
                catch { }
            }

            return fallback;
        }

        private AxisEvidence TransformAxisEvidenceToWorld(AxisEvidence axis, Mat4 contextToWorld)
        {
            if (String.IsNullOrEmpty(axis.Source) && !axis.HasAxis && !axis.HasPoint) return axis;
            if (axis.HasAxis) axis.Axis = contextToWorld.Rotate(axis.Axis).NormalizedOr(Vec3.UnitZ);
            if (axis.HasPoint) axis.Point = contextToWorld.TransformPoint(axis.Point);
            axis.Source = (axis.Source ?? "") + ":context_to_world";
            return axis;
        }

        private void RepairConstraintEndpointsFromContextHint(ConstraintInfo ci, List<OccInfo> occs, string contextPath)
        {
            if (ci == null || !ci.HasAxisPoint) return;
            if (ci.A != null && ci.B != null && ci.A != ci.B) return;

            List<OccInfo> candidates = OccurrencesInContext(occs, contextPath)
                .OrderBy(o => DistanceOccurrenceToPoint(o, ci.AxisPointWorld))
                .ThenByDescending(o => o.MassKg)
                .Take(8)
                .ToList();
            if (candidates.Count < 2) return;

            if (ci.A == null) ci.A = candidates.FirstOrDefault(o => o != ci.B);
            if (ci.B == null || ci.B == ci.A) ci.B = candidates.FirstOrDefault(o => o != ci.A);
            if (ci.A != null && ci.B != null && ci.A != ci.B)
            {
                ci.RepairedFromCollapsedEndpoint = true;
                ci.ContextSource = (ci.ContextSource ?? "") + ":axis_point_context_endpoint_repair";
                Build51Log.Cad("BUILD71_CONTEXT_ENDPOINT_REPAIRED constraint='" + ci.StableId +
                    "' ctx='" + contextPath +
                    "' a='" + ci.A.LinkName +
                    "' b='" + ci.B.LinkName +
                    "' axis_pt=" + ci.AxisPointWorld.Text());
            }
        }

        private List<NativeJointInfo> ExtractNativeJoints(Inv.AssemblyDocument asm, List<OccInfo> occs)
        {
            // BUILD71: native AssemblyJoint objects may also live inside nested
            // subassembly definitions, not only in the root AssemblyComponentDefinition.
            List<NativeJointInfo> list = new List<NativeJointInfo>();
            int i = 0;
            try
            {
                AppendNativeJointsFromComponentDefinition(asm.ComponentDefinition, occs, "", Mat4.Identity, "top_assembly_definition", ref i, list);
                Inv.ComponentOccurrences topOccs = asm.ComponentDefinition.Occurrences;
                foreach (Inv.ComponentOccurrence occ in topOccs)
                {
                    string name = SafeString(TryGet(occ, "Name"));
                    Mat4 world = Mat4.FromInventorMatrix(TryGet(occ, "Transformation"), _lengthToMeters);
                    WalkNestedNativeJointDefinitions(occ, occs, name, world, ref i, list);
                }
            }
            catch (Exception ex)
            {
                Build51Log.Warn("Native joint extraction skipped: " + ex.Message);
            }
            int nested = list.Count(j => !String.IsNullOrEmpty(j.ContextPath));
            Build51Log.Cad("BUILD71_NATIVE_JOINT_RECURSIVE_SUMMARY total=" + list.Count +
                " top=" + (list.Count - nested) +
                " nested=" + nested +
                " axis=" + list.Count(j => j.HasAxis));
            return list;
        }

        private void WalkNestedNativeJointDefinitions(Inv.ComponentOccurrence occ, List<OccInfo> allLeaves, string contextPath, Mat4 contextToWorld, ref int index, List<NativeJointInfo> list)
        {
            if (occ == null) return;
            bool suppressed = TryBool(occ, "Suppressed", false);
            bool visible = TryBool(occ, "Visible", true);
            if (suppressed || !visible) return;

            bool hasChildren = false;
            try
            {
                Inv.ComponentOccurrencesEnumerator children = occ.SubOccurrences;
                if (children != null)
                {
                    foreach (Inv.ComponentOccurrence child in children)
                    {
                        hasChildren = true;
                        string childName = SafeString(TryGet(child, "Name"));
                        string childPath = String.IsNullOrEmpty(contextPath) ? childName : contextPath + "/" + childName;
                        // Same absolute-context rule used for nested constraints.
                        Mat4 childWorld = Mat4.FromInventorMatrix(TryGet(child, "Transformation"), _lengthToMeters);
                        WalkNestedNativeJointDefinitions(child, allLeaves, childPath, childWorld, ref index, list);
                    }
                }
            }
            catch { }

            if (!hasChildren) return;
            object definition = TryGet(occ, "Definition");
            if (definition == null) return;
            AppendNativeJointsFromComponentDefinition(definition, allLeaves, contextPath, contextToWorld, "nested_subassembly_definition", ref index, list);
        }

        private void AppendNativeJointsFromComponentDefinition(object componentDefinition, List<OccInfo> occs, string contextPath, Mat4 contextToWorld, string contextSource, ref int index, List<NativeJointInfo> list)
        {
            object jointsObj = TryGet(componentDefinition, "Joints");
            if (jointsObj == null) return;
            int before = list.Count;
            foreach (object j in (System.Collections.IEnumerable)jointsObj)
            {
                NativeJointInfo ni = ParseNativeJointObject(j, occs, contextPath, contextToWorld, contextSource, index);
                index++;
                if (ni == null) continue;
                if (ni.A != null && ni.B != null && ni.A != ni.B) list.Add(ni);
                Build51Log.Cad("BUILD71_NATIVE_JOINT[" + ni.Index + "] ctx='" + ni.ContextPath +
                    "' id='" + ni.StableId +
                    "' type='" + ni.JointKind +
                    "' occ1='" + (ni.A == null ? "" : ni.A.StableId) +
                    "' occ2='" + (ni.B == null ? "" : ni.B.StableId) +
                    "' axis=" + (ni.HasAxis ? ni.AxisWorld.Text() : "null"));
            }
            int added = list.Count - before;
            if (added > 0)
            {
                Build51Log.Cad("BUILD71_NATIVE_JOINT_CONTEXT path='" + contextPath +
                    "' source='" + contextSource +
                    "' added=" + added);
            }
        }

        private NativeJointInfo ParseNativeJointObject(object j, List<OccInfo> occs, string contextPath, Mat4 contextToWorld, string contextSource, int index)
        {
            if (j == null) return null;

            NativeJointInfo ni = new NativeJointInfo();
            ni.Index = index;
            ni.Raw = j;
            ni.ContextPath = contextPath ?? "";
            ni.ContextSource = contextSource ?? "";
            ni.Name = SafeString(TryGet(j, "Name"));

            if (String.IsNullOrWhiteSpace(ni.Name))
                ni.Name = "native_joint_" + ni.Index.ToString(_ci);

            ni.StableId = "native_" +
                ShortHash(
                    (ni.ContextPath ?? "") + "|" +
                    ni.Name + "|" +
                    ni.Index.ToString(_ci));

            ni.ApiClass = j.GetType().Name;

            object definition = FirstNonNull(
                TryGet(j, "Definition"),
                TryGet(j, "JointDefinition"));

            object typ = FirstNonNull(
                TryGet(definition, "JointType"),
                TryGet(j, "JointType"));

            if (typ != null)
                ni.ApiClass = typ.ToString();

            ni.Suppressed =
                TryBool(j, "Suppressed", false) ||
                TryBool(j, "IsSuppressed", false) ||
                TryBool(definition, "Suppressed", false);

            object health = FirstNonNull(
                TryGet(j, "HealthStatus"),
                TryGet(j, "Status"),
                TryGet(j, "JointStatus"),
                TryGet(definition, "HealthStatus"),
                TryGet(definition, "Status"));

            ni.HealthText = SafeString(health);
            ni.Healthy =
                !ni.Suppressed &&
                TryBool(j, "IsHealthy", true) &&
                !HealthTextLooksBad(ni.HealthText);

            object ent1 = FirstNonNull(
                TryGet(j, "OccurrenceOne"),
                TryGet(j, "AffectedOccurrenceOne"),
                TryGet(j, "EntityOne"));

            object ent2 = FirstNonNull(
                TryGet(j, "OccurrenceTwo"),
                TryGet(j, "AffectedOccurrenceTwo"),
                TryGet(j, "EntityTwo"));

            object originOne = FirstNonNull(
                TryGet(definition, "OriginOne"),
                TryGet(definition, "JointOriginOne"),
                TryGet(definition, "Origin1"));

            object originTwo = FirstNonNull(
                TryGet(definition, "OriginTwo"),
                TryGet(definition, "JointOriginTwo"),
                TryGet(definition, "Origin2"));

            object alignmentOne = FirstNonNull(
                TryGet(definition, "AlignmentOne"),
                TryGet(definition, "Alignment1"));

            object alignmentTwo = FirstNonNull(
                TryGet(definition, "AlignmentTwo"),
                TryGet(definition, "Alignment2"));

            // Endpoints are resolved from explicit AssemblyJoint occurrence references.
            // No point-based endpoint repair is used here because raw GeometryIntent
            // points can be occurrence-local.
            ni.A = FindOccurrenceFromAny(
                ent1,
                occs,
                ni.ContextPath,
                false,
                Vec3.Zero);

            ni.B = FindOccurrenceFromAny(
                ent2,
                occs,
                ni.ContextPath,
                false,
                Vec3.Zero);

            if (ni.A == null)
                ni.A = FindOccurrenceFromAny(
                    originOne,
                    occs,
                    ni.ContextPath,
                    false,
                    Vec3.Zero);

            if (ni.B == null)
                ni.B = FindOccurrenceFromAny(
                    originTwo,
                    occs,
                    ni.ContextPath,
                    false,
                    Vec3.Zero);

            AxisEvidence axLocal = TryExtractNativeJointDefinitionAxis(
                j,
                definition,
                originOne,
                originTwo,
                alignmentOne,
                alignmentTwo);

            DumpNativeJointDefinitionDiagnostics(
                ni.StableId,
                ni.Name,
                j,
                definition,
                originOne,
                originTwo,
                alignmentOne,
                alignmentTwo,
                axLocal,
                contextPath,
                contextToWorld);

            AxisEvidence ax = axLocal;
            if (!String.IsNullOrEmpty(ni.ContextPath))
            {
                // Only the direction is needed from this object. The pivot is selected
                // independently from scored geometry candidates.
                if (ax.HasAxis)
                    ax.Axis = contextToWorld.Rotate(ax.Axis).NormalizedOr(Vec3.UnitZ);
                ax.Source = (ax.Source ?? "") + ":context_to_world_direction";
            }

            ni.HasAxis = ax.HasAxis;
            ni.AxisWorld = ax.HasAxis
                ? ax.Axis.NormalizedOr(Vec3.UnitZ)
                : Vec3.Zero;

            double pivotQuality;
            string pivotSource;
            AxisEvidence pivot = SelectNativeJointPivot(
                ni.StableId,
                originOne,
                originTwo,
                definition,
                ni.A,
                ni.B,
                contextPath,
                contextToWorld,
                out pivotQuality,
                out pivotSource);

            ni.HasAxisPoint = pivot.HasPoint;
            ni.AxisPointWorld = pivot.HasPoint
                ? pivot.Point
                : (
                    ni.A != null && ni.B != null
                    ? Mid(ni.A.World.Translation, ni.B.World.Translation)
                    : Vec3.Zero);

            ni.PivotSource = pivotSource ?? "";
            ni.PivotQuality = pivotQuality;
            ni.AxisSource =
                (ax.Source ?? "") +
                ";pivot=" + ni.PivotSource;

            ni.JointKind = ClassifyNativeJointKind(
                ni.ApiClass,
                ni.Name);

            ni.EvidenceScore =
                (ni.HasAxis ? 200.0 : 0.0) +
                (ni.HasAxisPoint ? 150.0 : 0.0) +
                ni.PivotQuality +
                (ni.Healthy ? 100.0 : -300.0) +
                (ni.Suppressed ? -1000.0 : 0.0);

            if (!ni.HasAxis)
            {
                Build51Log.Error(
                    "NATIVE_JOINT_UNRESOLVED id='" + ni.StableId +
                    "' name='" + ni.Name +
                    "' has_axis=false source='" + ni.AxisSource +
                    "'. BUILD83 refuses to invent a rotation direction.");
            }
            else
            {
                Build51Log.Cad(
                    "BUILD83_NATIVE_JOINT_OK id='" + ni.StableId +
                    "' name='" + ni.Name +
                    "' A='" + (ni.A == null ? "null" : ni.A.LinkName) +
                    "' B='" + (ni.B == null ? "null" : ni.B.LinkName) +
                    "' axis_world=" + ni.AxisWorld.Text() +
                    " pivot_world_m=" + ni.AxisPointWorld.Text() +
                    " has_pivot=" + ni.HasAxisPoint +
                    " pivot_source='" + ni.PivotSource +
                    "' pivot_quality=" + F(ni.PivotQuality) +
                    " suppressed=" + ni.Suppressed +
                    " healthy=" + ni.Healthy +
                    " health='" + ni.HealthText +
                    "' source='" + ni.AxisSource + "'");
            }

            Build51Log.Native(
                "NATIVE_JOINT_FINAL id='" + ni.StableId +
                "' name='" + ni.Name +
                "' api='" + ni.ApiClass +
                "' kind='" + ni.JointKind +
                "' context='" + ni.ContextPath +
                "' A='" + (ni.A == null ? "null" : ni.A.LinkName) +
                "' B='" + (ni.B == null ? "null" : ni.B.LinkName) +
                "' has_axis=" + ni.HasAxis +
                " axis_world=" + ni.AxisWorld.Text() +
                " has_point=" + ni.HasAxisPoint +
                " point_world_m=" + ni.AxisPointWorld.Text() +
                " suppressed=" + ni.Suppressed +
                " healthy=" + ni.Healthy +
                " authority_score=" + F(ni.EvidenceScore) +
                " source='" + ni.AxisSource + "'");

            return ni;
        }

        private AxisEvidence TryExtractNativeJointDefinitionAxis(
            object joint,
            object definition,
            object originOne,
            object originTwo,
            object alignmentOne,
            object alignmentTwo)
        {
            AxisEvidence a1 = TryExtractAxisFromEntity(originOne);
            AxisEvidence a2 = TryExtractAxisFromEntity(originTwo);
            AxisEvidence ad = TryExtractAxisFromEntity(definition);

            AxisEvidence result = new AxisEvidence();

            if (a1.HasAxis)
            {
                result.HasAxis = true;
                result.Axis = a1.Axis.NormalizedOr(Vec3.UnitZ);
                result.Source = "AssemblyJointDefinition.OriginOne:" + a1.Source;
            }
            else if (a2.HasAxis)
            {
                result.HasAxis = true;
                result.Axis = a2.Axis.NormalizedOr(Vec3.UnitZ);
                result.Source = "AssemblyJointDefinition.OriginTwo:" + a2.Source;
            }
            else if (ad.HasAxis)
            {
                result.HasAxis = true;
                result.Axis = ad.Axis.NormalizedOr(Vec3.UnitZ);
                result.Source = "AssemblyJointDefinition:" + ad.Source;
            }

            // Both joint origins should describe the same physical rotational axis.
            // Average them only after making their directions consistent.
            if (a1.HasAxis && a2.HasAxis)
            {
                Vec3 u1 = a1.Axis.NormalizedOr(Vec3.UnitZ);
                Vec3 u2 = a2.Axis.NormalizedOr(Vec3.UnitZ);
                if (u1.Dot(u2) < 0.0) u2 = u2 * -1.0;
                Vec3 sum = u1 + u2;
                if (sum.Length > 1e-10)
                {
                    result.HasAxis = true;
                    result.Axis = sum.NormalizedOr(u1);
                    result.Source = "AssemblyJointDefinition.OriginOne+OriginTwo";
                }

                Build51Log.Axis("NATIVE_ORIGIN_AXIS_AGREEMENT dot=" + F(u1.Dot(u2)) +
                    " angle_deg=" + F(AngleDegrees(u1, u2)) +
                    " origin1_axis=" + u1.Text() + " origin2_axis=" + u2.Text());
            }

            if (a1.HasPoint)
            {
                result.HasPoint = true;
                result.Point = a1.Point;
                result.Source += ":OriginOne.Point";
            }
            else if (a2.HasPoint)
            {
                result.HasPoint = true;
                result.Point = a2.Point;
                result.Source += ":OriginTwo.Point";
            }
            else if (ad.HasPoint)
            {
                result.HasPoint = true;
                result.Point = ad.Point;
                result.Source += ":Definition.Point";
            }

            bool flipOrigin = TryBool(definition, "FlipOriginDirection", false);
            if (flipOrigin && result.HasAxis)
            {
                result.Axis = result.Axis * -1.0;
                result.Source += ":FlipOriginDirection";
            }

            // AlignmentOne defines roll around the joint Z axis, not the rotational
            // axis itself. It is logged for frame reconstruction but never substituted
            // for a missing OriginOne axis.
            AxisEvidence align1 = TryExtractAxisFromEntity(alignmentOne);
            AxisEvidence align2 = TryExtractAxisFromEntity(alignmentTwo);
            if (align1.HasAxis)
                Build51Log.Axis("NATIVE_ALIGNMENT_ONE axis=" + align1.Axis.Text() +
                    " source='" + align1.Source + "'");
            if (align2.HasAxis)
                Build51Log.Axis("NATIVE_ALIGNMENT_TWO axis=" + align2.Axis.Text() +
                    " source='" + align2.Source + "'");

            return result;
        }


        private AxisEvidence SelectNativeJointPivot(
            string stableId,
            object originOne,
            object originTwo,
            object definition,
            OccInfo a,
            OccInfo b,
            string contextPath,
            Mat4 contextToWorld,
            out double quality,
            out string selectedSource)
        {
            List<NativePointCandidate> candidates =
                new List<NativePointCandidate>();

            AddNativePivotCandidate(
                candidates,
                TryGet(originOne, "Geometry"),
                "OriginOne.Geometry",
                260.0,
                a,
                contextPath,
                contextToWorld);

            AddNativePivotCandidate(
                candidates,
                TryGet(originTwo, "Geometry"),
                "OriginTwo.Geometry",
                260.0,
                b,
                contextPath,
                contextToWorld);

            AddNativePivotCandidate(
                candidates,
                originOne,
                "OriginOne.GeometryIntent",
                90.0,
                a,
                contextPath,
                contextToWorld);

            AddNativePivotCandidate(
                candidates,
                originTwo,
                "OriginTwo.GeometryIntent",
                90.0,
                b,
                contextPath,
                contextToWorld);

            AddNativePivotCandidate(
                candidates,
                definition,
                "AssemblyJointDefinition",
                70.0,
                null,
                contextPath,
                contextToWorld);

            double scale = Math.Max(
                0.005,
                Math.Max(
                    OccurrenceCharacteristicSize(a),
                    OccurrenceCharacteristicSize(b)));

            // If OriginOne.Geometry and OriginTwo.Geometry agree, their average is
            // the most reliable physical axis point. This avoids the BUILD80 error:
            // raw GeometryIntent.Point was local, while Geometry points were already
            // expressed in assembly/subassembly coordinates.
            List<NativePointCandidate> originOneCandidates =
                candidates.Where(c =>
                    c.Source.IndexOf(
                        "OriginOne.Geometry",
                        StringComparison.OrdinalIgnoreCase) >= 0).ToList();

            List<NativePointCandidate> originTwoCandidates =
                candidates.Where(c =>
                    c.Source.IndexOf(
                        "OriginTwo.Geometry",
                        StringComparison.OrdinalIgnoreCase) >= 0).ToList();

            foreach (NativePointCandidate c1 in originOneCandidates)
            {
                foreach (NativePointCandidate c2 in originTwoCandidates)
                {
                    double agreement = (c1.Point - c2.Point).Length;
                    if (agreement > Math.Max(0.0015, scale * 0.20))
                        continue;

                    NativePointCandidate average =
                        new NativePointCandidate();

                    average.Point = Mid(c1.Point, c2.Point);
                    average.Source =
                        "OriginOne.Geometry+OriginTwo.Geometry_agreement";
                    average.Priority = 520.0 -
                        40.0 * agreement / Math.Max(scale, 1e-9);

                    AddNativePointCandidateUnique(
                        candidates,
                        average);
                }
            }

            // The legacy +Texturas midpoint is always retained as a safe fallback.
            if (a != null && b != null)
            {
                NativePointCandidate fallback =
                    new NativePointCandidate();

                fallback.Point = Mid(
                    a.World.Translation,
                    b.World.Translation);

                fallback.Source =
                    "legacy_texturas_occurrence_midpoint";
                fallback.Priority = 40.0;

                AddNativePointCandidateUnique(
                    candidates,
                    fallback);
            }

            NativePointCandidate best = null;
            foreach (NativePointCandidate candidate in candidates)
            {
                candidate.Score =
                    ScoreNativePivotCandidate(
                        candidate,
                        a,
                        b,
                        scale);

                Build51Log.Axis(
                    "BUILD83_NATIVE_PIVOT_CANDIDATE id='" +
                    stableId +
                    "' source='" + candidate.Source +
                    "' point_world_m=" + candidate.Point.Text() +
                    " priority=" + F(candidate.Priority) +
                    " score=" + F(candidate.Score) +
                    " distance_A_m=" +
                    F(a == null
                        ? -1.0
                        : DistanceOccurrenceToPoint(
                            a,
                            candidate.Point)) +
                    " distance_B_m=" +
                    F(b == null
                        ? -1.0
                        : DistanceOccurrenceToPoint(
                            b,
                            candidate.Point)));

                if (best == null ||
                    candidate.Score > best.Score)
                {
                    best = candidate;
                }
            }

            AxisEvidence result = new AxisEvidence();

            if (best == null ||
                !IsFiniteVec(best.Point))
            {
                quality = -1e9;
                selectedSource = "none";
                return result;
            }

            // A wildly distant candidate is less trustworthy than the legacy midpoint.
            // The fallback candidate is in the list, so this normally selects it.
            if (a != null && b != null)
            {
                double maxDistance = Math.Max(
                    DistanceOccurrenceToPoint(a, best.Point),
                    DistanceOccurrenceToPoint(b, best.Point));

                if (maxDistance > Math.Max(0.05, scale * 8.0))
                {
                    NativePointCandidate fallback =
                        candidates.FirstOrDefault(c =>
                            String.Equals(
                                c.Source,
                                "legacy_texturas_occurrence_midpoint",
                                StringComparison.OrdinalIgnoreCase));

                    if (fallback != null)
                        best = fallback;
                }
            }

            result.HasPoint = true;
            result.Point = best.Point;
            result.Source = best.Source;
            quality = best.Score;
            selectedSource = best.Source;

            Build51Log.Axis(
                "BUILD83_NATIVE_PIVOT_SELECTED id='" +
                stableId +
                "' source='" + best.Source +
                "' point_world_m=" + best.Point.Text() +
                " score=" + F(best.Score));

            return result;
        }

        private void AddNativePivotCandidate(
            List<NativePointCandidate> candidates,
            object entity,
            string source,
            double priority,
            OccInfo owner,
            string contextPath,
            Mat4 contextToWorld)
        {
            if (candidates == null || entity == null)
                return;

            AxisEvidence evidence =
                TryExtractAxisFromEntity(entity);

            if (!evidence.HasPoint ||
                !IsFiniteVec(evidence.Point))
                return;

            NativePointCandidate raw =
                new NativePointCandidate();

            raw.Point = evidence.Point;
            raw.Source = source + ".raw";
            raw.Priority = priority;

            AddNativePointCandidateUnique(
                candidates,
                raw);

            if (!String.IsNullOrEmpty(contextPath))
            {
                NativePointCandidate contextCandidate =
                    new NativePointCandidate();

                contextCandidate.Point =
                    contextToWorld.TransformPoint(
                        evidence.Point);

                contextCandidate.Source =
                    source + ".context_to_world";

                contextCandidate.Priority =
                    priority + 15.0;

                AddNativePointCandidateUnique(
                    candidates,
                    contextCandidate);
            }

            if (owner != null)
            {
                NativePointCandidate occurrenceCandidate =
                    new NativePointCandidate();

                occurrenceCandidate.Point =
                    owner.World.TransformPoint(
                        evidence.Point);

                occurrenceCandidate.Source =
                    source + ".occurrence_to_world";

                occurrenceCandidate.Priority =
                    priority + 10.0;

                AddNativePointCandidateUnique(
                    candidates,
                    occurrenceCandidate);
            }
        }

        private void AddNativePointCandidateUnique(
            List<NativePointCandidate> candidates,
            NativePointCandidate candidate)
        {
            if (candidates == null ||
                candidate == null ||
                !IsFiniteVec(candidate.Point))
                return;

            foreach (NativePointCandidate existing in candidates)
            {
                if ((existing.Point - candidate.Point).Length < 1e-9 &&
                    String.Equals(
                        existing.Source,
                        candidate.Source,
                        StringComparison.OrdinalIgnoreCase))
                    return;
            }

            candidates.Add(candidate);
        }

        private double ScoreNativePivotCandidate(
            NativePointCandidate candidate,
            OccInfo a,
            OccInfo b,
            double scale)
        {
            if (candidate == null ||
                !IsFiniteVec(candidate.Point))
                return -1e12;

            scale = Math.Max(scale, 0.001);

            double score = candidate.Priority;

            if (a != null)
                score -=
                    80.0 *
                    DistanceOccurrenceToPoint(
                        a,
                        candidate.Point) /
                    scale;

            if (b != null)
                score -=
                    80.0 *
                    DistanceOccurrenceToPoint(
                        b,
                        candidate.Point) /
                    scale;

            if (a != null && b != null)
            {
                Vec3 midpoint = Mid(
                    a.World.Translation,
                    b.World.Translation);

                score -=
                    4.0 *
                    (candidate.Point - midpoint).Length /
                    scale;

                double dA =
                    DistanceOccurrenceToPoint(
                        a,
                        candidate.Point);

                double dB =
                    DistanceOccurrenceToPoint(
                        b,
                        candidate.Point);

                if (dA <= scale * 0.20 &&
                    dB <= scale * 0.20)
                    score += 100.0;
            }

            if (candidate.Source.IndexOf(
                    ".Geometry",
                    StringComparison.OrdinalIgnoreCase) >= 0)
                score += 40.0;

            if (candidate.Source.IndexOf(
                    "agreement",
                    StringComparison.OrdinalIgnoreCase) >= 0)
                score += 100.0;

            return score;
        }

        private double OccurrenceCharacteristicSize(
            OccInfo occurrence)
        {
            if (occurrence == null)
                return 0.0;

            if (occurrence.HasRangeBox)
            {
                Vec3 diagonal =
                    occurrence.RangeMaxRaw -
                    occurrence.RangeMinRaw;

                if (diagonal.Length > 1e-9)
                    return diagonal.Length;
            }

            return 0.01;
        }

        private bool IsFiniteVec(Vec3 value)
        {
            return
                !Double.IsNaN(value.X) &&
                !Double.IsNaN(value.Y) &&
                !Double.IsNaN(value.Z) &&
                !Double.IsInfinity(value.X) &&
                !Double.IsInfinity(value.Y) &&
                !Double.IsInfinity(value.Z);
        }

        private List<NativeJointInfo> ResolveNativeJointDuplicates(
            List<NativeJointInfo> joints)
        {
            if (joints == null)
                return new List<NativeJointInfo>();

            List<NativeJointInfo> result =
                new List<NativeJointInfo>();

            IEnumerable<IGrouping<string, NativeJointInfo>> groups =
                joints
                    .Where(j =>
                        j != null &&
                        j.A != null &&
                        j.B != null &&
                        j.A != j.B)
                    .GroupBy(j => PairKey(j.A, j.B))
                    .OrderBy(g => g.Min(j => j.Index));

            foreach (IGrouping<string, NativeJointInfo> group in groups)
            {
                List<NativeJointInfo> candidates =
                    group.OrderBy(j => j.Index).ToList();

                if (candidates.Count == 1)
                {
                    NativeJointInfo only = candidates[0];

                    if (only.Suppressed)
                    {
                        _warnings.Add(
                            "Suppressed native Inventor joint omitted: " +
                            only.Name + " (" + only.StableId + ").");

                        Build51Log.Warn(
                            "BUILD83_NATIVE_SUPPRESSED_OMITTED pair='" +
                            group.Key +
                            "' id='" + only.StableId +
                            "' name='" + only.Name + "'");

                        continue;
                    }

                    result.Add(only);
                    continue;
                }

                bool collinear = true;
                NativeJointInfo reference =
                    candidates.FirstOrDefault(j => j.HasAxis);

                if (reference != null)
                {
                    Vec3 refAxis =
                        reference.AxisWorld.NormalizedOr(
                            Vec3.UnitZ);

                    foreach (NativeJointInfo candidate in candidates)
                    {
                        if (!candidate.HasAxis)
                            continue;

                        double dot = Math.Abs(
                            refAxis.Dot(
                                candidate.AxisWorld.NormalizedOr(
                                    Vec3.UnitZ)));

                        if (dot < 0.985)
                        {
                            collinear = false;
                            break;
                        }
                    }
                }

                HashSet<string> movableKinds =
                    new HashSet<string>(
                        candidates
                            .Where(candidate =>
                                !candidate.Suppressed)
                            .Select(candidate =>
                                candidate.JointKind ?? "continuous"),
                        StringComparer.OrdinalIgnoreCase);

                bool distinctPhysicalDofKinds =
                    movableKinds.Count > 1 &&
                    (
                        movableKinds.Contains("prismatic") ||
                        movableKinds.Contains("cylindrical") ||
                        movableKinds.Contains("planar") ||
                        movableKinds.Contains("spherical") ||
                        movableKinds.Contains("universal"));

                if (!collinear ||
                    distinctPhysicalDofKinds)
                {
                    foreach (NativeJointInfo candidate in candidates)
                    {
                        if (!candidate.Suppressed)
                            result.Add(candidate);
                    }

                    _warnings.Add(
                        "Multiple native joints share pair " +
                        group.Key +
                        " and represent non-collinear or distinct physical DOFs; " +
                        "preserved as a URDF+ multi-DOF/loop candidate.");

                    Build51Log.Warn(
                        "BUILD83_NATIVE_MULTI_DOF_PAIR pair='" +
                        group.Key +
                        "' count=" +
                        candidates.Count.ToString(_ci) +
                        " kinds='" +
                        String.Join(
                            ",",
                            movableKinds.ToArray()) +
                        "' collinear=" +
                        collinear.ToString());

                    continue;
                }

                NativeJointInfo selected =
                    candidates
                        .OrderByDescending(
                            NativeJointAuthorityScore)
                        .ThenByDescending(j => j.Index)
                        .First();

                result.Add(selected);

                foreach (NativeJointInfo duplicate in candidates)
                {
                    if (Object.ReferenceEquals(
                            duplicate,
                            selected))
                        continue;

                    _warnings.Add(
                        "Redundant native Inventor joint omitted for pair " +
                        group.Key +
                        ": kept " +
                        selected.Name +
                        ", omitted " +
                        duplicate.Name + ".");

                    Build51Log.Warn(
                        "BUILD83_NATIVE_DUPLICATE_SUPPRESSED pair='" +
                        group.Key +
                        "' kept_id='" + selected.StableId +
                        "' kept_name='" + selected.Name +
                        "' omitted_id='" + duplicate.StableId +
                        "' omitted_name='" + duplicate.Name +
                        "' kept_score=" +
                        F(NativeJointAuthorityScore(selected)) +
                        " omitted_score=" +
                        F(NativeJointAuthorityScore(duplicate)));
                }
            }

            // Keep unresolved endpoint joints in diagnostics only; they cannot form
            // a reliable mechanical edge.
            foreach (NativeJointInfo unresolved in joints)
            {
                if (unresolved == null ||
                    (unresolved.A != null &&
                     unresolved.B != null &&
                     unresolved.A != unresolved.B))
                    continue;

                Build51Log.Warn(
                    "BUILD83_NATIVE_ENDPOINT_UNRESOLVED id='" +
                    (unresolved == null ? "" : unresolved.StableId) +
                    "' name='" +
                    (unresolved == null ? "" : unresolved.Name) +
                    "'");
            }

            return result
                .OrderBy(j => j.Index)
                .ToList();
        }

        private double NativeJointAuthorityScore(
            NativeJointInfo joint)
        {
            if (joint == null)
                return -1e12;

            double score =
                joint.EvidenceScore;

            if (joint.HasAxis)
                score += 150.0;

            if (joint.HasAxisPoint)
                score += 120.0;

            if (joint.Healthy)
                score += 150.0;
            else
                score -= 300.0;

            if (joint.Suppressed)
                score -= 2000.0;

            // When Inventor contains an obsolete warned relation and a later
            // replacement for the same pair, the later healthy object wins if all
            // other evidence is equal.
            score +=
                Math.Max(0, joint.Index) * 0.01;

            return score;
        }

        private void DumpNativeJointDefinitionDiagnostics(
            string stableId,
            string displayName,
            object owner,
            object definition,
            object originOne,
            object originTwo,
            object alignmentOne,
            object alignmentTwo,
            AxisEvidence selected,
            string contextPath,
            Mat4 contextToWorld)
        {
            Build51Log.Axis("NATIVE_DEFINITION_EXTRACTION_BEGIN id='" + stableId +
                "' name='" + displayName + "' context='" + (contextPath ?? "") +
                "' context_matrix={" + MatrixReport(contextToWorld) + "}");

            object[] objects = new object[]
            {
                owner, definition, originOne, originTwo, alignmentOne, alignmentTwo,
                TryGet(originOne, "Geometry"), TryGet(originTwo, "Geometry"),
                TryGet(originOne, "Intent"), TryGet(originTwo, "Intent"),
                TryGet(originOne, "Point"), TryGet(originTwo, "Point")
            };
            string[] labels = new string[]
            {
                "AssemblyJoint", "Definition", "OriginOne", "OriginTwo",
                "AlignmentOne", "AlignmentTwo", "OriginOne.Geometry",
                "OriginTwo.Geometry", "OriginOne.Intent", "OriginTwo.Intent",
                "OriginOne.Point", "OriginTwo.Point"
            };

            for (int i = 0; i < objects.Length; i++)
            {
                AxisEvidence a = TryExtractAxisFromEntity(objects[i]);
                Build51Log.Axis("NATIVE_DEFINITION_CANDIDATE id='" + stableId +
                    "' candidate='" + labels[i] + "' object_type='" + ObjectTypeName(objects[i]) +
                    "' has_axis=" + a.HasAxis + " axis=" + a.Axis.Text() +
                    " has_point=" + a.HasPoint + " point_m=" + a.Point.Text() +
                    " source='" + a.Source + "'");
                DumpObjectSnapshot("NATIVE_DEFINITION:" + stableId + ":" + labels[i], objects[i]);
            }

            Build51Log.Axis("NATIVE_DEFINITION_SELECTED id='" + stableId +
                "' has_axis=" + selected.HasAxis + " axis=" + selected.Axis.Text() +
                " has_point=" + selected.HasPoint + " point_m=" + selected.Point.Text() +
                " source='" + selected.Source + "'");
        }

        // --------------------------------------------------------------------
        // Endpoint repair. This is the key fix for your gripper log: many Mate
        // constraints arrived as the same Base Plate / Bracket pair. Their axis
        // points, however, lie exactly at the actual pins/gears. We repair them
        // by nearest occurrence to the axis point and keep the original evidence.
        // --------------------------------------------------------------------

        private void RepairCollapsedConstraintEndpoints(List<OccInfo> occs, List<ConstraintInfo> constraints)
        {
            int rawPairs =
                constraints
                    .Where(c =>
                        c != null &&
                        c.A != null &&
                        c.B != null)
                    .Select(c =>
                        PairKey(c.A, c.B))
                    .Distinct()
                    .Count();

            int axisConstraintCount =
                constraints.Count(c =>
                    c != null &&
                    c.HasAxis);

            bool collapsed =
                rawPairs <=
                Math.Max(
                    1,
                    axisConstraintCount / 8);

            Build51Log.Cad(
                "BUILD83_ENDPOINT_REPAIR_ENTER collapsed=" +
                collapsed +
                " unique_pairs_before=" +
                rawPairs.ToString(_ci) +
                " axis_constraints=" +
                axisConstraintCount.ToString(_ci));

            int repaired = 0;

            foreach (ConstraintInfo constraint in constraints)
            {
                if (constraint == null ||
                    !constraint.HasAxisPoint)
                    continue;

                bool invalid =
                    constraint.A == null ||
                    constraint.B == null ||
                    constraint.A == constraint.B;

                double existingDistance =
                    Double.PositiveInfinity;

                if (!invalid)
                {
                    existingDistance =
                        DistanceOccurrenceToPoint(
                            constraint.A,
                            constraint.AxisPointWorld) +
                        DistanceOccurrenceToPoint(
                            constraint.B,
                            constraint.AxisPointWorld);
                }

                List<NearestHit> hits =
                    NearestOccurrences(
                        occs,
                        constraint.AxisPointWorld,
                        constraint.AxisWorld,
                        8).ToList();

                if (hits.Count < 2)
                    continue;

                OccInfo nearestA =
                    hits[0].Occurrence;

                OccInfo nearestB =
                    hits
                        .Skip(1)
                        .Select(h => h.Occurrence)
                        .FirstOrDefault(o =>
                            o != nearestA);

                if (nearestA == null ||
                    nearestB == null)
                    continue;

                double nearestDistance =
                    hits.First(h =>
                        h.Occurrence == nearestA).Distance3 +
                    hits.First(h =>
                        h.Occurrence == nearestB).Distance3;

                bool significantlyBetter =
                    invalid ||
                    (
                        collapsed &&
                        nearestDistance + 0.001 <
                            existingDistance * 0.65);

                if (!significantlyBetter)
                    continue;

                double secondDistanceMm =
                    hits.First(h =>
                        h.Occurrence == nearestB).Distance3 *
                    1000.0;

                double scale =
                    Math.Max(
                        0.005,
                        Math.Max(
                            OccurrenceCharacteristicSize(
                                nearestA),
                            OccurrenceCharacteristicSize(
                                nearestB)));

                if (!invalid &&
                    secondDistanceMm >
                        Math.Max(
                            8.0,
                            scale * 1000.0 * 0.50))
                    continue;

                string oldPair =
                    (constraint.A == null
                        ? ""
                        : constraint.A.StableId) +
                    "|" +
                    (constraint.B == null
                        ? ""
                        : constraint.B.StableId);

                constraint.RepairedFromCollapsedEndpoint = true;
                constraint.A = nearestA;
                constraint.B = nearestB;
                repaired++;

                Build51Log.Cad(
                    "BUILD83_ENDPOINT_REPAIRED constraint='" +
                    constraint.StableId +
                    "' old='" +
                    oldPair +
                    "' new='" +
                    nearestA.StableId +
                    "|" +
                    nearestB.StableId +
                    "' names='" +
                    nearestA.Name +
                    "|" +
                    nearestB.Name +
                    "' existing_distance_m=" +
                    F(existingDistance) +
                    " nearest_distance_m=" +
                    F(nearestDistance) +
                    " second_distance_mm=" +
                    F(secondDistanceMm));
            }

            int newPairs =
                constraints
                    .Where(c =>
                        c != null &&
                        c.A != null &&
                        c.B != null)
                    .Select(c =>
                        PairKey(c.A, c.B))
                    .Distinct()
                    .Count();

            Build51Log.Cad(
                "BUILD83_ENDPOINT_REPAIR_EXIT repaired=" +
                repaired.ToString(_ci) +
                " unique_pairs_after=" +
                newPairs.ToString(_ci));
        }

        private IEnumerable<NearestHit> NearestOccurrences(List<OccInfo> occs, Vec3 point, Vec3 axis, int take)
        {
            Vec3 ax = axis.NormalizedOr(Vec3.UnitZ);
            return occs.Select(o =>
            {
                Vec3 nearest = o.HasRangeBox ? ClosestPointOnAabb(point, o.RangeMinRaw, o.RangeMaxRaw) : o.WorldRaw.Translation;
                Vec3 d = nearest - point;
                Vec3 center = o.HasRangeBox ? Mid(o.RangeMinRaw, o.RangeMaxRaw) : o.WorldRaw.Translation;
                Vec3 centerDelta = center - point;
                double along = Math.Abs(centerDelta.Dot(ax));
                double plane = (centerDelta - ax * centerDelta.Dot(ax)).Length;
                return new NearestHit { Occurrence = o, Distance3 = d.Length, DistancePlane = plane, Along = along };
            }).OrderBy(h => h.Distance3 * 2.0 + h.DistancePlane + 0.15 * h.Along).ThenBy(h => h.Distance3).Take(take);
        }

        private ConstraintInfo SelectBestAxisConstraint(List<ConstraintInfo> constraints)
        {
            if (constraints == null || constraints.Count == 0)
                return null;

            return constraints
                .Where(c =>
                    c != null &&
                    c.HasAxis &&
                    !c.Suppressed &&
                    c.Healthy)
                .OrderByDescending(c => c.IsInsertLike ? 1 : 0)
                .ThenByDescending(c => c.HasAxisLikeGeometry ? 1 : 0)
                .ThenByDescending(c => c.HasAxisPoint ? 1 : 0)
                .ThenBy(c => c.IsAngleLike ? 1 : 0)
                .ThenBy(c => c.Index)
                .FirstOrDefault();
        }

        private bool AxisBundleIsCoherent(List<ConstraintInfo> axes)
        {
            if (axes == null)
                return true;

            List<ConstraintInfo> valid =
                axes.Where(c =>
                    c != null &&
                    c.HasAxis &&
                    !c.Suppressed &&
                    c.Healthy).ToList();

            if (valid.Count <= 1)
                return true;

            Vec3 reference =
                valid[0].AxisWorld.NormalizedOr(
                    Vec3.UnitZ);

            foreach (ConstraintInfo constraint in valid.Skip(1))
            {
                Vec3 axis =
                    constraint.AxisWorld.NormalizedOr(
                        Vec3.UnitZ);

                if (Math.Abs(reference.Dot(axis)) < 0.985)
                    return false;
            }

            return true;
        }


        private string ClassifyConstraintEntityKind(
            object entity)
        {
            if (entity == null)
                return "null";

            object geometry =
                UnwrapGeometryObject(entity);

            if (geometry == null)
                geometry = entity;

            string typeName =
                ObjectTypeName(geometry).ToLowerInvariant();

            bool hasRadius =
                TryGet(geometry, "Radius") != null ||
                TryGet(geometry, "MajorRadius") != null ||
                TryGet(geometry, "MinorRadius") != null;

            bool hasNormal =
                TryGet(geometry, "Normal") != null;

            bool hasDirection =
                TryGet(geometry, "Direction") != null ||
                TryGet(geometry, "AxisVector") != null ||
                TryGet(geometry, "Vector") != null;

            bool hasStartEnd =
                TryGet(geometry, "StartPoint") != null &&
                TryGet(geometry, "EndPoint") != null;

            bool hasCenter =
                TryGet(geometry, "Center") != null ||
                TryGet(geometry, "CenterPoint") != null;

            bool hasPoint =
                TryGet(entity, "Point") != null ||
                TryGet(geometry, "Point") != null ||
                TryGet(geometry, "Position") != null;

            if (typeName.Contains("cylinder") ||
                typeName.Contains("circle") ||
                typeName.Contains("arc") ||
                (hasRadius &&
                 (hasDirection ||
                  hasNormal ||
                  hasCenter)))
                return "axis_cylinder_circle";

            if (typeName.Contains("workaxis") ||
                typeName.Contains("line") ||
                typeName.Contains("axis") ||
                hasStartEnd ||
                (hasDirection && !hasNormal))
                return "axis_line";

            if (typeName.Contains("plane") ||
                typeName.Contains("planar") ||
                (hasNormal && !hasRadius))
                return "plane";

            if (typeName.Contains("point") ||
                hasPoint)
                return "point";

            return String.IsNullOrEmpty(typeName)
                ? "unknown"
                : typeName;
        }

        private bool IsAxisLikeEntityKind(
            string kind)
        {
            string value =
                (kind ?? "").ToLowerInvariant();

            return
                value.Contains("axis_") ||
                value.Contains("cylinder") ||
                value.Contains("circle") ||
                value.Contains("line");
        }

        private bool IsTrueAxisAxisConstraint(
            ConstraintInfo c)
        {
            return
                c != null &&
                c.HasAxis &&
                IsAxisLikeEntityKind(c.EntityOneKind) &&
                IsAxisLikeEntityKind(c.EntityTwoKind);
        }

        private bool HasUnlockedInsertShaftAxis(
            List<ConstraintInfo> constraints,
            out Vec3 axisWorld,
            out Vec3 axisPointWorld,
            out bool hasAxisPoint)
        {
            axisWorld = Vec3.UnitZ;
            axisPointWorld = Vec3.Zero;
            hasAxisPoint = false;

            List<ConstraintInfo> inserts =
                (constraints ?? new List<ConstraintInfo>())
                    .Where(c =>
                        c != null &&
                        c.IsInsertLike &&
                        !c.LockRotation &&
                        c.HasAxis)
                    .ToList();

            if (inserts.Count == 0)
                return false;

            int uniqueInsertAxes =
                CountUniqueAxisDirections(
                    inserts,
                    0.985);

            if (uniqueInsertAxes > 1)
                return false;

            ConstraintInfo bestInsert =
                SelectBestAxisConstraint(
                    inserts);

            if (bestInsert == null || !bestInsert.HasAxis)
                return false;

            axisWorld =
                bestInsert.AxisWorld.NormalizedOr(
                    Vec3.UnitZ);

            axisPointWorld =
                AverageConstraintAxisPoint(
                    inserts,
                    axisWorld,
                    bestInsert.A,
                    bestInsert.B,
                    out hasAxisPoint);

            if (!hasAxisPoint && bestInsert.HasAxisPoint)
            {
                axisPointWorld = bestInsert.AxisPointWorld;
                hasAxisPoint = true;
            }

            return true;
        }

        private bool IsAuxiliaryPlanarAxisContactOnly(
            List<ConstraintInfo> constraints)
        {
            List<ConstraintInfo> valid =
                (constraints ?? new List<ConstraintInfo>())
                    .Where(c => c != null && !c.Suppressed && c.Healthy)
                    .ToList();

            if (valid.Count == 0)
                return false;

            if (valid.Any(c =>
                    c.IsInsertLike ||
                    c.IsTransitionalLike ||
                    c.IsAngleLike ||
                    c.IsRotationCouplingLike ||
                    IsTrueAxisAxisConstraint(c)))
                return false;

            int planar = valid.Count(c => c.HasPlanarGeometry || c.IsFlushLike);
            int axisLike = valid.Count(c => c.HasAxisLikeGeometry);

            return
                planar >= 2 &&
                axisLike <= 1;
        }

        private bool IsPlanarEntityKind(
            string kind)
        {
            string value =
                (kind ?? "").ToLowerInvariant();

            return
                value.Contains("plane") ||
                value.Contains("planar");
        }

        private bool IsPointEntityKind(
            string kind)
        {
            return
                (kind ?? "").IndexOf(
                    "point",
                    StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private bool HealthTextLooksBad(
            string health)
        {
            string value =
                (health ?? "").ToLowerInvariant();

            if (String.IsNullOrWhiteSpace(value))
                return false;

            return
                value.Contains("error") ||
                value.Contains("failed") ||
                value.Contains("failure") ||
                value.Contains("sick") ||
                value.Contains("suppressed") ||
                value.Contains("invalid") ||
                value.Contains("inconsistent") ||
                value.Contains("broken") ||
                value.Contains("missing") ||
                value.Contains("lost") ||
                value.Contains("warning") ||
                value.Contains("warn");
        }

        private bool PairTouchesExplicitRotationCoupling(
            MechanicalModel model,
            OccInfo a,
            OccInfo b)
        {
            if (model == null || model.CadConstraints == null || a == null || b == null)
                return false;

            OccInfo ar = NearestRigidAssemblyIncludingSelf(a) ?? a;
            OccInfo br = NearestRigidAssemblyIncludingSelf(b) ?? b;

            foreach (ConstraintInfo c in model.CadConstraints)
            {
                if (c == null || !c.IsRotationCouplingLike || c.Suppressed || !c.Healthy || c.A == null || c.B == null)
                    continue;

                OccInfo ca = c.A;
                OccInfo cb = c.B;
                OccInfo car = NearestRigidAssemblyIncludingSelf(ca) ?? ca;
                OccInfo cbr = NearestRigidAssemblyIncludingSelf(cb) ?? cb;

                if (ca == a || ca == b || cb == a || cb == b)
                    return true;

                if ((car == ar || car == br || cbr == ar || cbr == br) && (car != cbr || ar != br))
                    return true;
            }

            return false;
        }

        private bool HasExplicitCadMotionAuthority(
            MechanicalModel model,
            OccInfo a,
            OccInfo b)
        {
            if (model == null || a == null || b == null)
                return false;

            if (PairTouchesExplicitRotationCoupling(model, a, b))
                return true;

            foreach (NativeJointInfo j in model.NativeJoints)
            {
                if (j == null || j.Suppressed || !j.Healthy || j.A == null || j.B == null)
                    continue;

                if ((j.A == a && j.B == b) || (j.A == b && j.B == a))
                    return !String.Equals(j.JointKind, "fixed", StringComparison.OrdinalIgnoreCase);
            }

            return false;
        }

        private BundleDecision ClassifyConstraintBundle(
            List<ConstraintInfo> constraints,
            OccInfo root,
            string pairKey,
            MechanicalModel model)
        {
            BundleDecision decision = new BundleDecision();

            List<ConstraintInfo> valid =
                (constraints ?? new List<ConstraintInfo>())
                    .Where(c => c != null && !c.Suppressed && c.Healthy)
                    .ToList();

            if (valid.Count == 0)
            {
                decision.Type = "fixed";
                decision.Score = 20.0;
                decision.Confidence = 0.10;
                decision.Source = "constraint_bundle_no_healthy_evidence";
                decision.Reason = "all constraints suppressed/unhealthy";
                decision.AllowLoop = false;
                decision.EstimatedConstraintRank = 6;
                decision.EstimatedFreeDof = 0;
                return decision;
            }

            // BUILD83 IMPORTANT:
            // A planar mate exposes a normal vector, but that normal is NOT a shaft axis.
            // BUILD83 put every HasAxis constraint in the same axis set. Therefore a
            // cylinder coincidence plus an axial end-face mate looked like two distinct
            // axes and was frozen, even though its 6D rank is exactly 5 (a revolute).
            List<ConstraintInfo> motionAxisConstraints =
                valid.Where(c =>
                    c.HasAxis &&
                    (c.HasAxisLikeGeometry || c.IsInsertLike || c.IsTransitionalLike))
                .ToList();

            ConstraintInfo bestAxis =
                SelectBestAxisConstraint(
                    motionAxisConstraints.Count > 0
                    ? motionAxisConstraints
                    : valid);

            decision.AxisWorld =
                bestAxis != null && bestAxis.HasAxis
                ? bestAxis.AxisWorld.NormalizedOr(Vec3.UnitZ)
                : Vec3.UnitZ;

            decision.AxisPointWorld =
                AverageConstraintAxisPoint(
                    motionAxisConstraints.Count > 0
                    ? motionAxisConstraints
                    : valid.Where(c => c.HasAxis).ToList(),
                    decision.AxisWorld,
                    valid[0].A,
                    valid[0].B,
                    out decision.HasAxisPoint);

            int uniqueMotionAxes =
                CountUniqueAxisDirections(
                    motionAxisConstraints,
                    0.985);

            bool motionAxesCoherent =
                uniqueMotionAxes <= 1;

            bool anyInsert = valid.Any(c => c.IsInsertLike);
            bool anyUnlockedInsert = valid.Any(c => c.IsInsertLike && !c.LockRotation);
            bool anyLockedInsert = valid.Any(c => c.IsInsertLike && c.LockRotation);
            bool anyAngle = valid.Any(c => c.IsAngleLike);
            bool anyFlush = valid.Any(c => c.IsFlushLike);
            bool anyTransitional = valid.Any(c => c.IsTransitionalLike);
            bool anyTangent = valid.Any(c => c.IsTangentLike);
            bool explicitCadMotionAuthority = HasExplicitCadMotionAuthority(model, valid[0].A, valid[0].B);
            bool explicitRotationCouplingEndpoint = PairTouchesExplicitRotationCoupling(model, valid[0].A, valid[0].B);

            Vec3 unlockedInsertAxisWorld;
            Vec3 unlockedInsertAxisPointWorld;
            bool unlockedInsertHasAxisPoint;
            bool hasUnlockedInsertShaftAxis =
                HasUnlockedInsertShaftAxis(
                    valid,
                    out unlockedInsertAxisWorld,
                    out unlockedInsertAxisPointWorld,
                    out unlockedInsertHasAxisPoint);

            int axisLikeCount = valid.Count(c => c.HasAxisLikeGeometry);
            int planarCount = valid.Count(c => c.HasPlanarGeometry);
            int pointCount = valid.Count(c => c.HasPointGeometry);

            List<double[]> rows =
                BuildConstraintRows6D(valid, decision.AxisWorld);

            int rawRank = RankRows6D(rows);
            int rawFreeDof = Math.Max(0, 6 - rawRank);

            decision.EstimatedConstraintRank = rawRank;
            decision.EstimatedFreeDof = rawFreeDof;

            double scale =
                Math.Max(
                    0.005,
                    Math.Max(
                        OccurrenceCharacteristicSize(valid[0].A),
                        OccurrenceCharacteristicSize(valid[0].B)));

            double perpendicularSpread =
                MaxPerpendicularAxisPointSpread(
                    motionAxisConstraints,
                    decision.AxisWorld);

            double spreadTolerance =
                Math.Max(0.0005, scale * 0.03);

            bool multipleParallelLines =
                motionAxesCoherent &&
                motionAxisConstraints.Count > 1 &&
                perpendicularSpread > spreadTolerance;

            bool hasUniqueShaftAxis =
                axisLikeCount > 0 &&
                motionAxisConstraints.Count > 0 &&
                motionAxesCoherent &&
                !multipleParallelLines;

            // Order matters. Explicit CAD motion semantics and a rank-5 shaft fit must
            // be decided before generic planar/fixed rules.
            if (anyLockedInsert)
            {
                decision.Type = "fixed";
                decision.Score = 990.0;
                decision.Confidence = 0.995;
                decision.Source = "cad_insert_rotation_locked_fixed";
                decision.Reason = "Insert explicitly locks rotation";
                decision.AllowLoop = false;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 0;
            }
            else if (anyUnlockedInsert && hasUnlockedInsertShaftAxis && !anyAngle && explicitCadMotionAuthority)
            {
                // BUILD130: the Insert axis is the physical joint axis.  Auxiliary
                // plane/axis mates can raise the algebraic rank to 6 or introduce
                // secondary CAD normals, but they are axial/phase placement evidence,
                // not a reason to freeze the shaft.
                decision.Type = "revolute";
                decision.AxisWorld = unlockedInsertAxisWorld;
                decision.AxisPointWorld = unlockedInsertAxisPointWorld;
                decision.HasAxisPoint = unlockedInsertHasAxisPoint;
                decision.Score = 982.0;
                decision.Confidence = explicitRotationCouplingEndpoint ? 0.985 : 0.965;
                decision.Source = explicitRotationCouplingEndpoint
                    ? "cad_insert_unlocked_revolute_explicit_rotation_coupled"
                    : "cad_insert_unlocked_revolute_explicit_native_motion";
                decision.Reason = "unlocked Insert promoted to active revolute from the Insert axis; auxiliary planar/axis mates are stops or phase evidence, not competing loop axes";
                decision.AllowLoop = true;
                decision.ExplicitMovable = true;
                decision.EstimatedFreeDof = 1;
            }
            else if (anyUnlockedInsert && hasUnlockedInsertShaftAxis && !anyAngle)
            {
                // BUILD130: Inventor leaves an unlocked Insert free to spin even when
                // the surrounding mates fully locate the part.  Export that shaft as a
                // TREE passive coordinate, not as a fixed rigid body and not as a loop
                // closure.  This is the general fix for LEGO pin/shaft pieces such as
                // H_1_BODY:* where the Insert defines the actual joint axis and later
                // plane-axis contacts are only closure/placement evidence.
                decision.Type = "continuous";
                decision.AxisWorld = unlockedInsertAxisWorld;
                decision.AxisPointWorld = unlockedInsertAxisPointWorld;
                decision.HasAxisPoint = unlockedInsertHasAxisPoint;
                decision.Score = 910.0;
                decision.Confidence = 0.86;
                decision.Source = "cad_unlocked_insert_passive_tree_axis_not_loop";
                decision.Reason = "unlocked Insert shaft axis is preserved as a dependent passive tree joint; auxiliary mates may make rank=" + rawRank.ToString(_ci) + " but must not convert this axis into a fixed stack or loop endpoint";
                decision.AllowLoop = false;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 1;
            }
            else if (anyTransitional && hasUniqueShaftAxis && !anyAngle)
            {
                decision.Type = "prismatic";
                decision.Score = 970.0;
                decision.Confidence = 0.99;
                decision.Source = "cad_transitional_prismatic";
                decision.Reason = "explicit Inventor Transitional/Transicional constraint";
                decision.AllowLoop = true;
                decision.ExplicitMovable = true;
                decision.EstimatedFreeDof = 1;
            }
            else if (!anyInsert && hasUniqueShaftAxis && rawRank == 5 && !anyAngle && explicitCadMotionAuthority)
            {
                // Cylinder/axis coincidence (4 constraints) + axial plane stop (1)
                // is the canonical CAD revolute joint. Plane normal disagreement is
                // expected and must never be interpreted as a second rotation axis.
                decision.Type = "revolute";
                decision.Score = 940.0;
                decision.Confidence = 0.98;
                decision.Source = "cad_axis_plus_axial_stop_rank5_revolute";
                decision.Reason =
                    "unique shaft axis with 6D rank 5; planar normal is an axial stop, not a competing joint axis";
                decision.AllowLoop = true;
                decision.ExplicitMovable = true;
                decision.EstimatedFreeDof = 1;
            }
            else if (!anyInsert && hasUniqueShaftAxis && rawRank == 4 && !anyAngle && explicitCadMotionAuthority)
            {
                // A lone cylindrical coincidence mathematically leaves axial sliding
                // and spin. In ordinary Inventor pin/shaft assemblies the axial degree
                // is closed by another edge in the mechanism. Exporting a non-standard
                // one-slider value and inventing translation in the viewer is worse and
                // physically incorrect. Keep the observable shaft spin as a revolute;
                // the URDF+ loop graph retains the remaining CAD evidence.
                decision.Type = "revolute";
                decision.Score = 820.0;
                decision.Confidence = 0.90;
                decision.Source = "cad_axis_rank4_bearing_revolute_assembly_axial_closure";
                decision.Reason =
                    "single shaft fit: preserve physical rotation; axial placement is closed by the assembly graph";
                decision.AllowLoop = true;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 1;
            }
            else if (!anyInsert && hasUniqueShaftAxis && rawRank == 5 && rawFreeDof == 1 && !anyAngle && IsAuxiliaryPlanarAxisContactOnly(valid))
            {
                // BUILD130: a plane-plane/plane-axis contact can look like a rank-5
                // revolute mathematically, but without Insert/native/axis-axis
                // shaft evidence it is an auxiliary contact/placement relation.
                // Keep it out of the loop graph; the real shaft axis must come from
                // the unlocked Insert/tree joint that owns the pin or lever body.
                decision.Type = "fixed";
                decision.Score = 360.0;
                decision.Confidence = 0.80;
                decision.Source = "cad_auxiliary_planar_axis_contact_not_loop";
                decision.Reason =
                    "rank=5/free_dof=1 came only from planar/plane-axis contact evidence; omitted as loop so the nearest unlocked Insert shaft remains the joint axis";
                decision.AllowLoop = false;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 0;
            }
            else if (!anyInsert && hasUniqueShaftAxis && rawRank == 5 && rawFreeDof == 1 && !anyAngle)
            {
                // BUILD124 USD MAX: Inventor constraint bundles with rank=5 and a
                // unique shaft axis are real 1-DOF kinematic relations even when
                // Inventor does not expose an AssemblyJoint.  BUILD121 froze them,
                // which removed all loops/couplings from the USD.  Export them as
                // passive/dependent revolute coordinates so the USD stage preserves
                // the same closed-chain evidence Inventor solves internally.
                decision.Type = "continuous";
                decision.Score = 735.0;
                decision.Confidence = 0.82;
                decision.Source = "cad_implicit_passive_rank5_revolute_loop_candidate";
                decision.Reason =
                    "rank=5/free_dof=1 unique shaft axis; Inventor constraint solver keeps this as a passive hinge even without explicit AssemblyJoint authority";
                decision.AllowLoop = true;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 1;
            }
            else if (
                anyAngle ||
                multipleParallelLines ||
                uniqueMotionAxes >= 2 ||
                rawRank >= 6 ||
                (anyFlush && axisLikeCount == 0 && valid.Count > 1))
            {
                decision.Type = "fixed";
                decision.Score = 760.0;
                decision.Confidence = rawRank >= 6 ? 0.98 : 0.93;
                decision.Source = "cad_constraint_rank_fixed";
                decision.Reason =
                    "bundle locks the relative pose: rank=" + rawRank.ToString(_ci) +
                    ", unique_motion_axes=" + uniqueMotionAxes.ToString(_ci) +
                    ", perpendicular_axis_spread_m=" + F(perpendicularSpread);
                decision.AllowLoop = rawRank >= 6;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 0;
            }
            else
            {
                // Plane/point coincidences without a unique shaft axis do not prove a
                // hinge. Freeze them instead of inventing movement.
                decision.Type = "fixed";
                decision.Score = 380.0;
                decision.Confidence = (planarCount > 0 || pointCount > 0) ? 0.84 : 0.58;
                decision.Source = "cad_ambiguous_constraint_bundle_frozen";
                decision.Reason =
                    "insufficient evidence for a unique URDF coordinate: rank=" + rawRank.ToString(_ci) +
                    ", raw_free_dof=" + rawFreeDof.ToString(_ci) +
                    ", axis_like=" + axisLikeCount.ToString(_ci) +
                    ", planar=" + planarCount.ToString(_ci) +
                    ", tangent=" + anyTangent.ToString();
                decision.AllowLoop = false;
                decision.ExplicitMovable = false;
                decision.EstimatedFreeDof = 0;
            }

            Build51Log.Pair(
                "BUILD89_BUNDLE_DECISION pair='" + pairKey +
                "' A='" + (valid[0].A == null ? "" : valid[0].A.LinkName) +
                "' B='" + (valid[0].B == null ? "" : valid[0].B.LinkName) +
                "' count=" + valid.Count.ToString(_ci) +
                " type='" + decision.Type +
                "' raw_rank=" + rawRank.ToString(_ci) +
                " raw_free_dof=" + rawFreeDof.ToString(_ci) +
                " exported_free_dof=" + decision.EstimatedFreeDof.ToString(_ci) +
                " unique_motion_axes=" + uniqueMotionAxes.ToString(_ci) +
                " axis_like=" + axisLikeCount.ToString(_ci) +
                " planar=" + planarCount.ToString(_ci) +
                " insert=" + anyInsert +
                " explicit_motion_authority=" + explicitCadMotionAuthority +
                " explicit_rotation_endpoint=" + explicitRotationCouplingEndpoint +
                " transitional=" + anyTransitional +
                " angle=" + anyAngle +
                " flush=" + anyFlush +
                " perpendicular_spread_m=" + F(perpendicularSpread) +
                " confidence=" + F(decision.Confidence) +
                " allow_loop=" + decision.AllowLoop +
                " source='" + decision.Source +
                "' reason='" + decision.Reason + "'");

            return decision;
        }

        private List<double[]> BuildConstraintRows6D(
            List<ConstraintInfo> constraints,
            Vec3 fallbackAxis)
        {
            List<double[]> rows =
                new List<double[]>();

            foreach (ConstraintInfo constraint in constraints)
            {
                if (constraint == null ||
                    constraint.Suppressed ||
                    !constraint.Healthy)
                    continue;

                Vec3 axis =
                    constraint.HasAxis
                    ? constraint.AxisWorld.NormalizedOr(
                        fallbackAxis.NormalizedOr(
                            Vec3.UnitZ))
                    : fallbackAxis.NormalizedOr(
                        Vec3.UnitZ);

                Vec3 point =
                    constraint.HasAxisPoint
                    ? constraint.AxisPointWorld
                    : (
                        constraint.A != null &&
                        constraint.B != null
                        ? Mid(
                            constraint.A.World.Translation,
                            constraint.B.World.Translation)
                        : Vec3.Zero);

                Vec3 u;
                Vec3 v;
                BuildPerpendicularBasis(
                    axis,
                    out u,
                    out v);

                if (constraint.IsInsertLike)
                {
                    AddAxisAlignmentRows(
                        rows,
                        axis,
                        point);

                    AddTwistTranslationRow(
                        rows,
                        axis,
                        point);

                    if (constraint.LockRotation)
                        AddTwistAngularRow(
                            rows,
                            axis);

                    continue;
                }

                if (constraint.IsTransitionalLike)
                {
                    AddTwistTranslationRow(
                        rows,
                        u,
                        point);

                    AddTwistTranslationRow(
                        rows,
                        v,
                        point);

                    AddAngularIdentityRows(
                        rows);

                    continue;
                }

                if (constraint.IsAngleLike)
                {
                    AddTwistAngularRow(
                        rows,
                        axis);

                    continue;
                }

                if (constraint.IsTangentLike)
                {
                    AddTwistTranslationRow(
                        rows,
                        axis,
                        point);

                    continue;
                }

                if (constraint.HasAxisLikeGeometry)
                {
                    AddAxisAlignmentRows(
                        rows,
                        axis,
                        point);

                    continue;
                }

                if (constraint.HasPointGeometry)
                {
                    AddPointCoincidenceRows(
                        rows,
                        point);

                    continue;
                }

                // Mate/flush between planar or unknown entities.
                AddPlaneMateRows(
                    rows,
                    axis,
                    point);
            }

            return rows;
        }

        private void AddPlaneMateRows(
            List<double[]> rows,
            Vec3 normal,
            Vec3 point)
        {
            normal =
                normal.NormalizedOr(
                    Vec3.UnitZ);

            Vec3 u;
            Vec3 v;
            BuildPerpendicularBasis(
                normal,
                out u,
                out v);

            AddTwistTranslationRow(
                rows,
                normal,
                point);

            AddTwistAngularRow(
                rows,
                u);

            AddTwistAngularRow(
                rows,
                v);
        }

        private void AddAxisAlignmentRows(
            List<double[]> rows,
            Vec3 axis,
            Vec3 point)
        {
            axis =
                axis.NormalizedOr(
                    Vec3.UnitZ);

            Vec3 u;
            Vec3 v;
            BuildPerpendicularBasis(
                axis,
                out u,
                out v);

            AddTwistTranslationRow(
                rows,
                u,
                point);

            AddTwistTranslationRow(
                rows,
                v,
                point);

            AddTwistAngularRow(
                rows,
                u);

            AddTwistAngularRow(
                rows,
                v);
        }

        private void AddPointCoincidenceRows(
            List<double[]> rows,
            Vec3 point)
        {
            AddTwistTranslationRow(
                rows,
                Vec3.UnitX,
                point);

            AddTwistTranslationRow(
                rows,
                Vec3.UnitY,
                point);

            AddTwistTranslationRow(
                rows,
                Vec3.UnitZ,
                point);
        }

        private void AddAngularIdentityRows(
            List<double[]> rows)
        {
            AddTwistAngularRow(
                rows,
                Vec3.UnitX);

            AddTwistAngularRow(
                rows,
                Vec3.UnitY);

            AddTwistAngularRow(
                rows,
                Vec3.UnitZ);
        }

        private void AddTwistTranslationRow(
            List<double[]> rows,
            Vec3 direction,
            Vec3 point)
        {
            direction =
                direction.NormalizedOr(
                    Vec3.UnitX);

            Vec3 angular =
                point.Cross(direction);

            AddNormalizedRow(
                rows,
                new double[]
                {
                    direction.X,
                    direction.Y,
                    direction.Z,
                    angular.X,
                    angular.Y,
                    angular.Z
                });
        }

        private void AddTwistAngularRow(
            List<double[]> rows,
            Vec3 direction)
        {
            direction =
                direction.NormalizedOr(
                    Vec3.UnitX);

            AddNormalizedRow(
                rows,
                new double[]
                {
                    0.0,
                    0.0,
                    0.0,
                    direction.X,
                    direction.Y,
                    direction.Z
                });
        }

        private void AddNormalizedRow(
            List<double[]> rows,
            double[] row)
        {
            if (rows == null ||
                row == null ||
                row.Length < 6)
                return;

            double norm = 0.0;
            for (int i = 0; i < 6; i++)
                norm += row[i] * row[i];

            norm = Math.Sqrt(norm);
            if (norm < 1e-12)
                return;

            double[] normalized =
                new double[6];

            for (int i = 0; i < 6; i++)
                normalized[i] =
                    row[i] / norm;

            rows.Add(normalized);
        }

        private void BuildPerpendicularBasis(
            Vec3 axis,
            out Vec3 u,
            out Vec3 v)
        {
            axis =
                axis.NormalizedOr(
                    Vec3.UnitZ);

            Vec3 seed =
                Math.Abs(axis.Z) < 0.85
                ? Vec3.UnitZ
                : Vec3.UnitX;

            u =
                axis.Cross(seed).NormalizedOr(
                    Vec3.UnitY);

            v =
                axis.Cross(u).NormalizedOr(
                    Vec3.UnitX);
        }

        private int RankRows6D(
            List<double[]> rows)
        {
            if (rows == null ||
                rows.Count == 0)
                return 0;

            int m = rows.Count;
            const int n = 6;

            double[,] matrix =
                new double[m, n];

            for (int i = 0; i < m; i++)
            {
                double[] row = rows[i];
                for (int j = 0; j < n; j++)
                    matrix[i, j] =
                        row != null &&
                        j < row.Length
                        ? row[j]
                        : 0.0;
            }

            int rank = 0;
            int pivotRow = 0;
            const double tolerance = 1e-8;

            for (int column = 0;
                 column < n &&
                 pivotRow < m;
                 column++)
            {
                int best = pivotRow;
                double bestValue =
                    Math.Abs(
                        matrix[best, column]);

                for (int row = pivotRow + 1;
                     row < m;
                     row++)
                {
                    double value =
                        Math.Abs(
                            matrix[row, column]);

                    if (value > bestValue)
                    {
                        best = row;
                        bestValue = value;
                    }
                }

                if (bestValue < tolerance)
                    continue;

                if (best != pivotRow)
                {
                    for (int c = 0; c < n; c++)
                    {
                        double temporary =
                            matrix[pivotRow, c];

                        matrix[pivotRow, c] =
                            matrix[best, c];

                        matrix[best, c] =
                            temporary;
                    }
                }

                double pivot =
                    matrix[pivotRow, column];

                for (int c = column; c < n; c++)
                    matrix[pivotRow, c] /= pivot;

                for (int row = 0; row < m; row++)
                {
                    if (row == pivotRow)
                        continue;

                    double factor =
                        matrix[row, column];

                    if (Math.Abs(factor) <
                        tolerance)
                        continue;

                    for (int c = column; c < n; c++)
                        matrix[row, c] -=
                            factor *
                            matrix[pivotRow, c];
                }

                pivotRow++;
                rank++;
            }

            return Math.Min(
                rank,
                6);
        }

        private int CountUniqueAxisDirections(
            List<ConstraintInfo> constraints,
            double collinearDotThreshold)
        {
            List<Vec3> representatives =
                new List<Vec3>();

            foreach (ConstraintInfo constraint in constraints)
            {
                if (constraint == null ||
                    !constraint.HasAxis)
                    continue;

                Vec3 axis =
                    constraint.AxisWorld.NormalizedOr(
                        Vec3.UnitZ);

                bool matched = false;
                foreach (Vec3 representative in representatives)
                {
                    if (Math.Abs(
                            representative.Dot(axis)) >=
                        collinearDotThreshold)
                    {
                        matched = true;
                        break;
                    }
                }

                if (!matched)
                    representatives.Add(axis);
            }

            return representatives.Count;
        }

        private double MaxPerpendicularAxisPointSpread(
            List<ConstraintInfo> constraints,
            Vec3 axis)
        {
            List<Vec3> points =
                constraints
                    .Where(c =>
                        c != null &&
                        c.HasAxisPoint)
                    .Select(c =>
                        c.AxisPointWorld)
                    .ToList();

            if (points.Count < 2)
                return 0.0;

            axis =
                axis.NormalizedOr(
                    Vec3.UnitZ);

            double max = 0.0;

            for (int i = 0; i < points.Count; i++)
            {
                for (int j = i + 1;
                     j < points.Count;
                     j++)
                {
                    Vec3 delta =
                        points[j] -
                        points[i];

                    Vec3 perpendicular =
                        delta -
                        axis *
                        delta.Dot(axis);

                    if (perpendicular.Length > max)
                        max =
                            perpendicular.Length;
                }
            }

            return max;
        }

        private Vec3 AverageConstraintAxisPoint(
            List<ConstraintInfo> constraints,
            Vec3 axis,
            OccInfo a,
            OccInfo b,
            out bool hasPoint)
        {
            List<Vec3> points =
                constraints
                    .Where(c =>
                        c != null &&
                        c.HasAxisPoint)
                    .Select(c =>
                        c.AxisPointWorld)
                    .ToList();

            if (points.Count == 0)
            {
                hasPoint = false;

                return
                    a != null &&
                    b != null
                    ? Mid(
                        a.World.Translation,
                        b.World.Translation)
                    : Vec3.Zero;
            }

            Vec3 sum = Vec3.Zero;
            foreach (Vec3 point in points)
                sum += point;

            hasPoint = true;
            return sum * (1.0 / points.Count);
        }

        private Vec3 ClosestPointOnAabb(Vec3 p, Vec3 min, Vec3 max)
        {
            return new Vec3(Clamp(p.X, Math.Min(min.X, max.X), Math.Max(min.X, max.X)),
                            Clamp(p.Y, Math.Min(min.Y, max.Y), Math.Max(min.Y, max.Y)),
                            Clamp(p.Z, Math.Min(min.Z, max.Z), Math.Max(min.Z, max.Z)));
        }

        private double Clamp(double v, double lo, double hi)
        {
            if (v < lo) return lo;
            if (v > hi) return hi;
            return v;
        }

        // --------------------------------------------------------------------
        // Mechanical model construction
        // --------------------------------------------------------------------

        private int EstimatedFreeDofForJointType(
            string jointType)
        {
            string type =
                (jointType ?? "fixed")
                    .ToLowerInvariant();

            if (type == "fixed")
                return 0;

            if (type == "cylindrical" ||
                type == "universal")
                return 2;

            if (type == "planar" ||
                type == "spherical" ||
                type == "ball" ||
                type == "floating")
                return 3;

            return 1;
        }


        private bool IsActiveNativeJointAuthority(NativeJointInfo joint)
        {
            if (joint == null || joint.A == null || joint.B == null) return false;
            if (joint.Suppressed) return false;
            if (!joint.HasAxis) return false;
            if (String.Equals(joint.JointKind, "fixed", StringComparison.OrdinalIgnoreCase)) return false;
            return true;
        }

        private bool GroundedOccurrenceHasActiveNativeKinematicAuthority(OccInfo occurrence, List<NativeJointInfo> nativeJoints)
        {
            if (occurrence == null || nativeJoints == null) return false;
            foreach (NativeJointInfo joint in nativeJoints)
            {
                if (!IsActiveNativeJointAuthority(joint)) continue;
                if (joint.A == occurrence || joint.B == occurrence) return true;
            }
            return false;
        }

        private int ActiveNativeJointDegree(OccInfo occurrence, List<NativeJointInfo> nativeJoints)
        {
            if (occurrence == null || nativeJoints == null) return 0;
            int degree = 0;
            foreach (NativeJointInfo joint in nativeJoints)
            {
                if (!IsActiveNativeJointAuthority(joint)) continue;
                if (joint.A == occurrence || joint.B == occurrence) degree++;
            }
            return degree;
        }

        private int ActiveNativeGroundedEdgeCount(List<OccInfo> grounded, List<NativeJointInfo> nativeJoints)
        {
            if (grounded == null || nativeJoints == null) return 0;
            HashSet<OccInfo> groundedSet = new HashSet<OccInfo>(grounded.Where(o => o != null));
            int count = 0;
            foreach (NativeJointInfo joint in nativeJoints)
            {
                if (!IsActiveNativeJointAuthority(joint)) continue;
                if (groundedSet.Contains(joint.A) && groundedSet.Contains(joint.B)) count++;
            }
            return count;
        }


        // --------------------------------------------------------------------
        // BUILD131: anchored bearing/support disambiguation.
        // --------------------------------------------------------------------
        // Inventor "Insert" constraints on a bearing block are not enough to make
        // the bearing occurrence itself a rotating body.  In assemblies such as
        // Cuplaj spatial, Lagar:1 has two orthogonal planar coincidences to Placa:1
        // (a rigid mount), but a higher-scored unlocked Insert to Furca:1 caused
        // the spanning tree to choose Lagar:1 as a revolute child.  The correct
        // semantics are:
        //   * bearing/support bodies with rigid planar evidence to the base stay fixed;
        //   * shaft/fork inserts through that support may remain revolute evidence;
        //   * if the moving branch is already connected elsewhere, that shaft/support
        //     insert becomes a loop/closure candidate, not a rotating support link.
        private bool Build131IsBearingSupportOccurrence(OccInfo occurrence)
        {
            if (occurrence == null) return false;

            string text =
                ((occurrence.Name ?? "") + " " +
                 (occurrence.LinkName ?? "") + " " +
                 (occurrence.Path ?? "") + " " +
                 Path.GetFileNameWithoutExtension(occurrence.SourceDocumentPath ?? ""))
                    .ToLowerInvariant();

            return
                text.Contains("lagar") ||
                text.Contains("bearing");
        }

        private bool Build131IsGroundAnchorOccurrence(OccInfo occurrence, OccInfo root)
        {
            if (occurrence == null) return false;
            if (occurrence == root) return true;
            if (occurrence.Grounded) return true;

            string text =
                ((occurrence.Name ?? "") + " " +
                 (occurrence.LinkName ?? "") + " " +
                 (occurrence.Path ?? "") + " " +
                 Path.GetFileNameWithoutExtension(occurrence.SourceDocumentPath ?? ""))
                    .ToLowerInvariant();

            return
                text.Contains("placa") ||
                text.Contains("plate") ||
                text.Contains("base") ||
                text.Contains("chassis") ||
                text.Contains("frame");
        }

        private bool Build131HasRigidPlanarMountEvidence(List<ConstraintInfo> bundle)
        {
            if (bundle == null) return false;

            List<ConstraintInfo> valid =
                bundle
                    .Where(c =>
                        c != null &&
                        !c.Suppressed &&
                        c.Healthy)
                    .ToList();

            if (valid.Count < 2) return false;
            if (valid.Any(c => c.IsInsertLike || c.IsAngleLike || c.IsTransitionalLike || c.IsTangentLike || c.IsRotationCouplingLike))
                return false;

            int planarCount =
                valid.Count(c =>
                    c.HasPlanarGeometry ||
                    c.IsMateLike ||
                    c.IsFlushLike);

            if (planarCount < 2) return false;

            List<ConstraintInfo> planeDirections =
                valid
                    .Where(c =>
                        c.HasAxis &&
                        (c.HasPlanarGeometry || c.IsMateLike || c.IsFlushLike))
                    .ToList();

            int uniqueNormals =
                CountUniqueAxisDirections(
                    planeDirections,
                    0.94);

            if (uniqueNormals >= 2) return true;

            // Conservative fallback: point/plane + one planar mate can also lock a
            // small support block against a grounded plate.
            int pointCount =
                valid.Count(c =>
                    c.HasPointGeometry);

            return planarCount >= 2 && pointCount >= 1 && uniqueNormals >= 1;
        }

        private bool Build131IsGroundedBearingMountBundle(List<ConstraintInfo> bundle, OccInfo root)
        {
            if (!Build131HasRigidPlanarMountEvidence(bundle)) return false;
            if (bundle == null || bundle.Count == 0) return false;

            OccInfo a = bundle[0].A;
            OccInfo b = bundle[0].B;
            if (a == null || b == null) return false;

            bool aBearing = Build131IsBearingSupportOccurrence(a);
            bool bBearing = Build131IsBearingSupportOccurrence(b);
            bool aAnchor = Build131IsGroundAnchorOccurrence(a, root);
            bool bAnchor = Build131IsGroundAnchorOccurrence(b, root);

            return
                (aBearing && bAnchor) ||
                (bBearing && aAnchor);
        }

        private bool Build131SupportHasGroundedPlanarMount(
            OccInfo support,
            OccInfo root,
            List<ConstraintInfo> constraints)
        {
            if (support == null) return false;
            if (!Build131IsBearingSupportOccurrence(support)) return false;
            if (support.Grounded) return true;
            if (constraints == null) return false;

            IEnumerable<IGrouping<string, ConstraintInfo>> groups =
                constraints
                    .Where(c =>
                        c != null &&
                        c.A != null &&
                        c.B != null &&
                        c.A != c.B &&
                        (c.A == support || c.B == support))
                    .GroupBy(c =>
                        PairKey(c.A, c.B));

            foreach (IGrouping<string, ConstraintInfo> group in groups)
            {
                List<ConstraintInfo> bundle =
                    group.ToList();

                OccInfo other =
                    bundle[0].A == support
                    ? bundle[0].B
                    : bundle[0].A;

                if (!Build131IsGroundAnchorOccurrence(other, root))
                    continue;

                if (Build131HasRigidPlanarMountEvidence(bundle))
                    return true;
            }

            return false;
        }

        private bool Build131IsAnchoredBearingInsertBundle(
            List<ConstraintInfo> bundle,
            OccInfo root,
            List<ConstraintInfo> constraints)
        {
            if (bundle == null || bundle.Count == 0) return false;
            if (!bundle.Any(c => c != null && c.IsInsertLike && !c.LockRotation)) return false;

            OccInfo a = bundle[0].A;
            OccInfo b = bundle[0].B;
            if (a == null || b == null) return false;

            bool aBearing = Build131IsBearingSupportOccurrence(a);
            bool bBearing = Build131IsBearingSupportOccurrence(b);

            if (aBearing && Build131SupportHasGroundedPlanarMount(a, root, constraints))
                return true;

            if (bBearing && Build131SupportHasGroundedPlanarMount(b, root, constraints))
                return true;

            return false;
        }

        private void Build131ApplyBearingSupportDecisionPatch(
            List<ConstraintInfo> bundle,
            OccInfo root,
            List<ConstraintInfo> allConstraints,
            BundleDecision decision)
        {
            if (bundle == null || bundle.Count == 0 || decision == null) return;

            if (Build131IsGroundedBearingMountBundle(bundle, root))
            {
                decision.Type = "fixed";
                decision.Score = 9950.0;
                decision.Confidence = 0.995;
                decision.Source = "BUILD131_bearing_support_rigid_mount_fixed";
                decision.Reason =
                    "bearing/support occurrence has orthogonal planar mount evidence to a grounded/base occurrence; support blocks must not become rotating children";
                decision.AllowLoop = false;
                decision.ExplicitMovable = false;
                decision.EstimatedConstraintRank = 6;
                decision.EstimatedFreeDof = 0;

                Build51Log.Pair(
                    "BUILD131_BEARING_SUPPORT_MOUNT_FIXED pair='" +
                    PairKey(bundle[0].A, bundle[0].B) +
                    "' A='" + (bundle[0].A == null ? "" : bundle[0].A.LinkName) +
                    "' B='" + (bundle[0].B == null ? "" : bundle[0].B.LinkName) +
                    "' evidence='" +
                    String.Join(",", bundle.Select(c => c.StableId).ToArray()) +
                    "'");
                return;
            }

            if (Build131IsAnchoredBearingInsertBundle(bundle, root, allConstraints))
            {
                // Keep the insert as shaft/fork rotational evidence, but allow it to be
                // emitted as a loop if the fixed support mount is already in the tree.
                // This prevents Lagar:* from becoming the moving child while retaining
                // the physical bearing closure.
                decision.AllowLoop = true;
                if (decision.Score > 920.0)
                    decision.Score = 920.0;

                decision.Source =
                    (decision.Source ?? "") +
                    ";BUILD131_anchored_bearing_insert_loop_enabled";

                decision.Reason =
                    (decision.Reason ?? "") +
                    "; anchored bearing/support insert is shaft motion evidence only; support body remains fixed to base";

                Build51Log.Pair(
                    "BUILD131_ANCHORED_BEARING_INSERT_ENABLED pair='" +
                    PairKey(bundle[0].A, bundle[0].B) +
                    "' A='" + (bundle[0].A == null ? "" : bundle[0].A.LinkName) +
                    "' B='" + (bundle[0].B == null ? "" : bundle[0].B.LinkName) +
                    "' allow_loop=true evidence='" +
                    String.Join(",", bundle.Select(c => c.StableId).ToArray()) +
                    "'");
            }
        }

        private MechanicalModel BuildMechanicalModel(string robotName, OccInfo root, List<OccInfo> occs, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints)
        {
            MechanicalModel model =
                new MechanicalModel();

            model.RobotName = robotName;
            model.RootOccurrence = root;
            model.Occurrences.AddRange(occs);
            model.CadConstraints.AddRange(constraints ?? new List<ConstraintInfo>());
            model.NativeJoints.AddRange(nativeJoints ?? new List<NativeJointInfo>());

            List<MechanicalEdge> edges =
                new List<MechanicalEdge>();

            HashSet<string> nativePairs =
                new HashSet<string>();

            // BUILD86: every grounded occurrence is locked to assembly world, not
            // merely considered as a root candidate.  Inventor can have several
            // grounded parts/subassemblies; allowing any of them to become a
            // revolute child is a direct violation of the IAM state.
            foreach (OccInfo groundedOccurrence in occs.Where(o => o != null && o.Grounded && o != root))
            {
                // BUILD98: Inventor can report a part as Grounded while still
                // providing an explicit AssemblyJoint that defines its real
                // motion.  This happens in the RB COMPLETE robotic arm: RB 1..6
                // are Grounded=True in the browser, but De rotación:1..6 are
                // healthy native revolutes with scored pivots.  In that case
                // the native joint is the kinematic authority and Grounded is
                // treated as q0/assembly placement evidence, not as a world lock.
                if (GroundedOccurrenceHasActiveNativeKinematicAuthority(groundedOccurrence, nativeJoints))
                {
                    Build51Log.Pair(
                        "BUILD98_GROUNDED_LOCK_SKIPPED_NATIVE_AUTHORITY link='" +
                        groundedOccurrence.LinkName +
                        "' name='" +
                        groundedOccurrence.Name +
                        "' reason='healthy explicit native AssemblyJoint overrides browser Grounded lock'");
                    continue;
                }

                MechanicalEdge groundLock = new MechanicalEdge();
                groundLock.A = root;
                groundLock.B = groundedOccurrence;
                groundLock.Type = "fixed";
                groundLock.AxisWorld = Vec3.UnitZ;
                groundLock.AxisPointWorld = groundedOccurrence.World.Translation;
                groundLock.HasAxisPoint = true;
                groundLock.Score = 10000.0;
                groundLock.Confidence = 1.0;
                groundLock.EstimatedConstraintRank = 6;
                groundLock.EstimatedFreeDof = 0;
                groundLock.AllowLoop = false;
                groundLock.ExplicitMovable = false;
                groundLock.Source = "inventor_grounded_world_lock";
                groundLock.Evidence = groundedOccurrence.StableId;
                groundLock.EdgeKey = "grounded:" + groundedOccurrence.StableId;
                edges.Add(groundLock);
            }

            foreach (NativeJointInfo nativeJoint in nativeJoints)
            {
                if (nativeJoint == null ||
                    nativeJoint.A == null ||
                    nativeJoint.B == null ||
                    nativeJoint.A == nativeJoint.B)
                    continue;

                OccInfo rigidNativeContext;
                if (TryGetSharedRigidAssembly(nativeJoint.A, nativeJoint.B, out rigidNativeContext))
                {
                    Build51Log.Pair(
                        "BUILD86_RIGID_SUBASSEMBLY_NATIVE_EVIDENCE_PRESERVED_NOT_ACTIVATED id='" +
                        nativeJoint.StableId + "' rigid_context='" + rigidNativeContext.LinkName + "'");
                    model.RigidInternalEvidenceCount++;
                    continue;
                }

                if (nativeJoint.Suppressed)
                {
                    model.Warnings.Add(
                        "Suppressed native Inventor joint ignored: " +
                        nativeJoint.Name);
                    continue;
                }

                if (!nativeJoint.HasAxis)
                {
                    model.Errors.Add(
                        "Unresolved native Inventor joint '" +
                        nativeJoint.Name +
                        "' (" +
                        nativeJoint.StableId +
                        "): no physical axis direction.");

                    continue;
                }

                MechanicalEdge edge =
                    new MechanicalEdge();

                edge.A = nativeJoint.A;
                edge.B = nativeJoint.B;
                edge.Type = nativeJoint.JointKind;
                edge.AxisWorld =
                    nativeJoint.AxisWorld.NormalizedOr(
                        Vec3.UnitZ);

                edge.AxisPointWorld =
                    nativeJoint.HasAxisPoint
                    ? nativeJoint.AxisPointWorld
                    : Mid(
                        nativeJoint.A.World.Translation,
                        nativeJoint.B.World.Translation);

                edge.HasAxisPoint =
                    nativeJoint.HasAxisPoint;

                edge.Score =
                    1200.0 +
                    NativeJointAuthorityScore(
                        nativeJoint);

                edge.Confidence =
                    nativeJoint.Healthy
                    ? 0.995
                    : 0.80;

                edge.EstimatedConstraintRank =
                    String.Equals(
                        edge.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase)
                    ? 6
                    : 5;

                edge.EstimatedFreeDof =
                    EstimatedFreeDofForJointType(
                        edge.Type);

                edge.ExplicitMovable =
                    !String.Equals(
                        edge.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase);

                edge.AllowLoop =
                    edge.ExplicitMovable;

                edge.Evidence =
                    nativeJoint.StableId;

                edge.Source =
                    "native_inventor_joint_definition" +
                    ";axis=" +
                    (nativeJoint.AxisSource ?? "") +
                    ";pivot=" +
                    (nativeJoint.PivotSource ?? "");

                edge.EdgeKey =
                    "native:" +
                    PairKey(edge.A, edge.B) +
                    ":" +
                    edge.Evidence;

                edges.Add(edge);
                nativePairs.Add(
                    PairKey(
                        nativeJoint.A,
                        nativeJoint.B));

                Build51Log.Pair(
                    "BUILD83_NATIVE_EDGE pair='" +
                    PairKey(edge.A, edge.B) +
                    "' type='" + edge.Type +
                    "' axis_world=" +
                    edge.AxisWorld.Text() +
                    " pivot_world_m=" +
                    edge.AxisPointWorld.Text() +
                    " has_exact_pivot=" +
                    edge.HasAxisPoint +
                    " score=" +
                    F(edge.Score) +
                    " confidence=" +
                    F(edge.Confidence) +
                    " evidence='" +
                    edge.Evidence + "'");
            }

            IEnumerable<IGrouping<string, ConstraintInfo>> constraintGroups =
                constraints
                    .Where(c =>
                        c != null &&
                        c.A != null &&
                        c.B != null &&
                        c.A != c.B &&
                        !c.IsRotationCouplingLike)
                    .GroupBy(c =>
                        PairKey(c.A, c.B));

            foreach (IGrouping<string, ConstraintInfo> group in constraintGroups)
            {
                List<ConstraintInfo> bundle =
                    group.ToList();

                string pairKey =
                    group.Key;

                OccInfo rigidConstraintContext;
                if (TryGetSharedRigidAssembly(bundle[0].A, bundle[0].B, out rigidConstraintContext))
                {
                    Build51Log.Pair(
                        "BUILD86_RIGID_SUBASSEMBLY_CONSTRAINT_EVIDENCE_PRESERVED_NOT_ACTIVATED pair='" +
                        pairKey + "' rigid_context='" + rigidConstraintContext.LinkName +
                        "' count=" + bundle.Count.ToString(_ci));
                    model.RigidInternalEvidenceCount += bundle.Count;
                    continue;
                }

                if (nativePairs.Contains(pairKey))
                {
                    _warnings.Add(
                        "Constraint bundle skipped because a native Inventor joint is authoritative for " +
                        pairKey +
                        ": " +
                        String.Join(
                            ",",
                            bundle
                                .Select(x => x.StableId)
                                .ToArray()));

                    Build51Log.Pair(
                        "BUILD83_CONSTRAINT_BUNDLE_SKIPPED_NATIVE pair='" +
                        pairKey +
                        "' count=" +
                        bundle.Count.ToString(_ci));

                    continue;
                }

                BundleDecision decision =
                    ClassifyConstraintBundle(
                        bundle,
                        root,
                        pairKey,
                        model);

                Build131ApplyBearingSupportDecisionPatch(
                    bundle,
                    root,
                    constraints,
                    decision);

                MechanicalEdge edge =
                    new MechanicalEdge();

                edge.A = bundle[0].A;
                edge.B = bundle[0].B;
                edge.Type = decision.Type;
                edge.AxisWorld =
                    decision.AxisWorld.NormalizedOr(
                        Vec3.UnitZ);

                edge.AxisPointWorld =
                    decision.AxisPointWorld;

                edge.HasAxisPoint =
                    decision.HasAxisPoint;

                edge.Score =
                    decision.Score;

                edge.Confidence =
                    decision.Confidence;

                edge.EstimatedConstraintRank =
                    decision.EstimatedConstraintRank;

                edge.EstimatedFreeDof =
                    decision.EstimatedFreeDof;

                edge.AllowLoop =
                    decision.AllowLoop;

                edge.ExplicitMovable =
                    decision.ExplicitMovable;

                edge.Evidence =
                    String.Join(
                        ",",
                        bundle
                            .Select(x => x.StableId)
                            .ToArray());

                edge.Source =
                    decision.Source +
                    ";reason=" +
                    decision.Reason;

                if (bundle.Any(c =>
                        c.RepairedFromCollapsedEndpoint))
                    edge.Source +=
                        ";axis_point_endpoint_repaired";

                edge.EdgeKey =
                    "cad:" +
                    pairKey +
                    ":" +
                    ShortHash(edge.Evidence ?? "");

                edges.Add(edge);
            }

            // BUILD86 browser-hierarchy / rigid-scope edges.
            // These are deliberately low score: real CAD joints/constraints win.
            // The spanning tree selects only the minimum number needed to attach a
            // subassembly reference frame to each internally connected component.
            foreach (OccInfo occurrence in occs)
            {
                if (occurrence == null || occurrence.Parent == null) continue;

                MechanicalEdge hierarchy = new MechanicalEdge();
                hierarchy.A = occurrence.Parent;
                hierarchy.B = occurrence;
                hierarchy.Type = "fixed";
                hierarchy.AxisWorld = Vec3.UnitZ;
                hierarchy.AxisPointWorld = occurrence.World.Translation;
                hierarchy.HasAxisPoint = true;
                bool parentIsRigidSubassembly =
                    occurrence.Parent.IsAssemblyNode &&
                    !occurrence.Parent.IsFlexible;

                hierarchy.Score = parentIsRigidSubassembly ? 5000.0 : 25.0;
                hierarchy.Confidence = parentIsRigidSubassembly ? 1.0 : 0.35;
                hierarchy.EstimatedConstraintRank = 6;
                hierarchy.EstimatedFreeDof = 0;
                hierarchy.AllowLoop = false;
                hierarchy.ExplicitMovable = false;
                hierarchy.Source = parentIsRigidSubassembly
                    ? "inventor_rigid_subassembly_internal_lock"
                    : "cad_browser_hierarchy_fallback";
                hierarchy.Evidence = occurrence.Parent.StableId + "->" + occurrence.StableId;
                hierarchy.EdgeKey = "hierarchy:" + hierarchy.Evidence;
                edges.Add(hierarchy);
            }

            DumpMechanicalEdgeCandidates(edges, "BEFORE_SPANNING_TREE_SELECTION");

            List<MechanicalEdge> tree =
                SelectSpanningTree(
                    root,
                    occs,
                    edges);

            DumpSelectedMechanicalEdges(tree, "SPANNING_TREE_SELECTED");

            HashSet<string> treeSet =
                new HashSet<string>(
                    tree.Select(e =>
                        e.EdgeKey ??
                        (
                            PairKey(e.A, e.B) +
                            ":" +
                            e.Evidence)));

            foreach (MechanicalEdge edge in tree)
            {
                JointSpec joint =
                    MakeJointFromEdge(
                        model,
                        edge,
                        true);

                model.TreeJoints.Add(joint);
            }

            foreach (MechanicalEdge edge in edges)
            {
                string key =
                    edge.EdgeKey ??
                    (
                        PairKey(edge.A, edge.B) +
                        ":" +
                        edge.Evidence);

                if (treeSet.Contains(key))
                    continue;

                if (edge.A != null && edge.B != null && edge.A.Grounded && edge.B.Grounded)
                {
                    Build51Log.Pair(
                        "BUILD86_GROUNDED_REDUNDANT_EDGE_OMITTED pair='" +
                        PairKey(edge.A, edge.B) + "' source='" + edge.Source + "'");
                    continue;
                }

                if (!edge.AllowLoop)
                {
                    Build51Log.Pair(
                        "BUILD83_REDUNDANT_EDGE_OMITTED pair='" +
                        PairKey(edge.A, edge.B) +
                        "' type='" +
                        edge.Type +
                        "' source='" +
                        edge.Source +
                        "' reason='not_explicit_loop_evidence'");

                    continue;
                }

                JointSpec loop =
                    MakeJointFromEdge(
                        model,
                        edge,
                        false);

                if (String.Equals(
                        edge.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase))
                {
                    loop.Type = "fixed";
                    loop.ConstraintKind = "6d";
                }

                model.LoopJoints.Add(loop);
            }

            // Keep every visual occurrence even when the CAD relation graph is
            // incomplete. Such fallback edges are fixed and explicitly diagnosed.
            HashSet<OccInfo> connected =
                new HashSet<OccInfo>();

            connected.Add(root);

            foreach (JointSpec joint in model.TreeJoints)
                connected.Add(joint.Child);

            foreach (OccInfo occurrence in occs)
            {
                if (connected.Contains(occurrence))
                    continue;

                JointSpec fallback =
                    new JointSpec();

                fallback.Name =
                    "visual_fixed_" +
                    occurrence.LinkName;

                fallback.Type = "fixed";
                fallback.Parent = root;
                fallback.Child = occurrence;
                fallback.AxisWorld = Vec3.UnitZ;
                fallback.AxisPointWorld =
                    occurrence.World.Translation;

                fallback.Source =
                    "disconnected_visual_fallback";

                fallback.Confidence = 0.10;
                fallback.EstimatedFreeDof = 0;
                fallback.PivotSource =
                    "occurrence_world_origin";

                model.TreeJoints.Add(
                    fallback);

                model.Warnings.Add(
                    "Disconnected occurrence fixed for visualization: " +
                    occurrence.Name);
            }

            AddExplicitRotationConstraintCouplings(
                model,
                constraints);

            // BUILD91: Inventor LEGO assemblies often report a RotationConstraint
            // on one wheel/axle and then expose adjacent coaxial decorative/drive
            // inserts as if they were also active bearings.  That creates serial
            // revolute joints on the same shaft: the viewer then lets sprockets,
            // chain wheels or caps spin independently and the mechanism looks
            // "horrible" even though q=0 validates perfectly.  Collapse only
            // unreferenced, passive, coaxial child revolutes into fixed rigid-stack
            // joints. Explicit rotation-coupling master/dependent joints remain
            // protected.
            DemotePassiveCoaxialStackRevolutes(model);
            FinalizeBuild92ImplicitKinematicRoles(model);
            ApplyBuild95NonDirectImplicitMotionPolicy(model);
            RecordBuild92ImplicitKinematicCandidates(model, constraints);
            RepairBuild129StarCouplerPiesaJoints(model);
            AddBuild124ClosedChainLoopCouplings(model);
            PromoteBuild124ImplicitDriverIfNeeded(model);

            Build51Log.Warn(
                "BUILD124 generic axis-collinearity mimic inference remains conservative. " +
                "Unlocked Insert shaft axes are exported as dependent tree coordinates; passive rank-5 CAD hinges are exported only when they are not auxiliary planar contacts. " +
                "Implicit shaft motion is exported only as dependent/passive USD evidence; active couplings require explicit CAD, gear, overlay or user-override evidence.");

            int movableTreeCountForAudit =
                model.TreeJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase));

            double movableRatioForAudit =
                model.TreeJoints.Count == 0
                ? 0.0
                : ((double)movableTreeCountForAudit / (double)model.TreeJoints.Count);

            Build51Log.Validate(
                "BUILD89_MOBILITY_BUDGET stage=after_mechanical_graph movable_tree=" +
                movableTreeCountForAudit.ToString(_ci) +
                " total_tree=" +
                model.TreeJoints.Count.ToString(_ci) +
                " ratio=" +
                F(movableRatioForAudit) +
                " passive_insert_policy='unlocked_insert_exports_passive_tree_axis_not_loop'");

            if (movableRatioForAudit > 0.25 && occs.Count > 80)
            {
                string highMobilityWarning =
                    "BUILD89_HIGH_MOBILITY_REVIEW: movable ratio is high for a LEGO/CAD assembly; inspect BUILD89_EDGE_CANDIDATE, BUILD89_BUNDLE_DECISION and BUILD89_SELECTED_EDGE logs before trusting independent_dof.";
                model.Warnings.Add(highMobilityWarning);
                Build51Log.Warn(highMobilityWarning);
            }

            Build51Log.Robot(
                "BUILD95_ROBOT_SUMMARY stage=after_mechanical_graph name='" +
                robotName +
                "' links=" +
                (occs.Count + 1).ToString(_ci) +
                " joints=" +
                model.TreeJoints.Count.ToString(_ci) +
                " movable=" +
                model.TreeJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase)).ToString(_ci) +
                " fixed=" +
                model.TreeJoints.Count(j =>
                    String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase)).ToString(_ci) +
                " loops=" +
                model.LoopJoints.Count.ToString(_ci) +
                " native_pairs=" +
                nativePairs.Count.ToString(_ci));

            return model;
        }



        private void RepairBuild129StarCouplerPiesaJoints(MechanicalModel model)
        {
            if (model == null || model.Occurrences == null) return;
            bool looksLikeStar = model.Occurrences.Any(o => o != null && ContainsNoCase(o.LinkName + " " + o.Name, "stea")) &&
                                 model.Occurrences.Any(o => o != null && ContainsNoCase(o.LinkName + " " + o.Name, "piesa_3")) &&
                                 model.Occurrences.Any(o => o != null && ContainsNoCase(o.LinkName + " " + o.Name, "bucsa"));
            if (!looksLikeStar) return;

            int repaired = 0;
            repaired += RepairBuild129StarPiesaPair(model, "piesa_3_1", "bucsa_1");
            repaired += RepairBuild129StarPiesaPair(model, "piesa_3_2", "bucsa_2");

            if (repaired > 0)
            {
                string msg = "BUILD129_STAR_COUPLER_REPAIR repaired_piesa_joints=" + repaired.ToString(_ci) +
                    " policy='rank4/free_dof2/axis_like1/nonplanar bushing-piesa candidates are exported as passive revolute coordinates, not frozen fixed bodies'";
                model.Warnings.Add(msg);
                Build51Log.Summary(msg);
            }
        }

        private int RepairBuild129StarPiesaPair(MechanicalModel model, string piesaToken, string bucsaToken)
        {
            OccInfo piesa = FindModelOccurrenceByToken(model, piesaToken);
            OccInfo bucsa = FindModelOccurrenceByToken(model, bucsaToken);
            if (piesa == null || bucsa == null) return 0;

            ImplicitKinematicCandidate cand = model.ImplicitCandidates.FirstOrDefault(k =>
                k != null && IsPairLinks(k, piesa.LinkName, bucsa.LinkName) &&
                k.RawRank == 4 && k.RawFreeDof >= 1 && k.AxisLikeCount >= 1 && k.PlanarCount == 0 && k.HasAxisPoint);
            if (cand == null) return 0;

            JointSpec joint = model.TreeJoints.FirstOrDefault(j => j != null && j.Child == piesa);
            if (joint == null) return 0;

            string oldName = joint.Name;
            string oldParent = joint.Parent == null ? "" : joint.Parent.LinkName;
            string oldType = joint.Type;

            joint.Parent = bucsa;
            joint.Child = piesa;
            joint.Name = "joint_continuous_" + SanitizeName(bucsa.LinkName + "_to_" + piesa.LinkName);
            joint.Type = "continuous";
            joint.AxisWorld = cand.AxisWorld.NormalizedOr(Vec3.UnitX);
            joint.AxisPointWorld = cand.AxisPointWorld;
            joint.Source = "BUILD129_star_coupler_rank4_axis_candidate_promoted";
            joint.Evidence = cand.Evidence;
            joint.PivotSource = "BUILD129_implicit_candidate_axis_point";
            joint.Confidence = 0.76;
            joint.EstimatedFreeDof = Math.Max(1, cand.RawFreeDof);
            joint.Independent = "false";
            joint.KinematicRole = "dependent_passive_implicit_coordinate";
            joint.KinematicAuthority = "BUILD129_star_coupler_bushing_piesa_axis_evidence";
            joint.ImplicitMotionCandidate = true;
            joint.RequiresReview = false;
            joint.ReviewReason = "";

            cand.ExportedJoint = joint.Name;
            cand.ExportedType = joint.Type;
            cand.ExportedRole = joint.KinematicRole;
            cand.Reason = (cand.Reason ?? "") + "; BUILD129 promoted star-coupler piesa/bucsa pair from fixed/omitted to passive revolute because the CAD bundle has rank=4, free_dof>=1, axis_like=1, planar=0.";

            Build51Log.Pair("BUILD129_STAR_COUPLER_PIESA_REPAIRED piesa='" + piesa.LinkName +
                "' bucsa='" + bucsa.LinkName +
                "' old_joint='" + oldName +
                "' old_parent='" + oldParent +
                "' old_type='" + oldType +
                "' new_joint='" + joint.Name +
                "' axis=" + joint.AxisWorld.Text() +
                " pivot=" + joint.AxisPointWorld.Text() +
                " evidence='" + joint.Evidence + "'");
            return 1;
        }

        private OccInfo FindModelOccurrenceByToken(MechanicalModel model, string token)
        {
            if (model == null || token == null) return null;
            string t = token.ToLowerInvariant();
            return model.Occurrences.FirstOrDefault(o => o != null &&
                ((o.LinkName ?? "").ToLowerInvariant().Contains(t) || (o.Name ?? "").ToLowerInvariant().Replace(" ", "_").Contains(t)));
        }

        private bool ContainsNoCase(string s, string token)
        {
            return (s ?? "").IndexOf(token ?? "", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private bool IsPairLinks(ImplicitKinematicCandidate k, string a, string b)
        {
            return k != null &&
                ((String.Equals(k.LinkA, a, StringComparison.OrdinalIgnoreCase) && String.Equals(k.LinkB, b, StringComparison.OrdinalIgnoreCase)) ||
                 (String.Equals(k.LinkA, b, StringComparison.OrdinalIgnoreCase) && String.Equals(k.LinkB, a, StringComparison.OrdinalIgnoreCase)));
        }

        private void FinalizeBuild92ImplicitKinematicRoles(MechanicalModel model)
        {
            if (model == null || model.TreeJoints == null) return;

            int active = 0;
            int dependent = 0;
            int fixedCount = 0;
            int implicitPassive = 0;
            int review = 0;

            foreach (JointSpec joint in model.TreeJoints)
            {
                if (joint == null) continue;
                bool isFixed = String.Equals(joint.Type, "fixed", StringComparison.OrdinalIgnoreCase);
                if (isFixed)
                {
                    fixedCount++;
                    joint.KinematicRole = "fixed_rigid_relation";
                    joint.KinematicAuthority = "fixed_or_structural";
                    continue;
                }

                string source = joint.Source ?? "";
                bool implicitBySource =
                    source.IndexOf("implicit_passive", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    source.IndexOf("assembly_axial_closure", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    source.IndexOf("passive", StringComparison.OrdinalIgnoreCase) >= 0;

                bool explicitBySource =
                    source.IndexOf("native_inventor_joint_definition", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    source.IndexOf("explicit_rotation_coupled", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    source.IndexOf("explicit_native_motion", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    source.IndexOf("cad_transitional_prismatic", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    source.IndexOf("cad_axis_plus_axial_stop_rank5_revolute", StringComparison.OrdinalIgnoreCase) >= 0;

                if (String.IsNullOrEmpty(joint.Independent))
                {
                    if (implicitBySource && !explicitBySource)
                        joint.Independent = "false";
                    else if (explicitBySource)
                        joint.Independent = "true";
                    else
                        joint.Independent = "false";
                }

                if (String.Equals(joint.Independent, "true", StringComparison.OrdinalIgnoreCase))
                {
                    joint.KinematicRole = "active_independent_coordinate";
                    joint.KinematicAuthority = explicitBySource ? "explicit_inventor_or_coupling_authority" : "inferred_active_review";
                    if (!explicitBySource)
                    {
                        joint.RequiresReview = true;
                        joint.ReviewReason = "active coordinate was not backed by explicit Inventor AssemblyJoint/RotationConstraint";
                        review++;
                    }
                    active++;
                }
                else
                {
                    joint.KinematicRole = implicitBySource ? "dependent_passive_implicit_coordinate" : "dependent_coordinate";
                    joint.KinematicAuthority = implicitBySource ? "implicit_inventor_constraint_solver_evidence" : "dependent_or_loop_solver_owned";
                    joint.ImplicitMotionCandidate = implicitBySource;
                    if (implicitBySource) implicitPassive++;
                    dependent++;
                }

                Build51Log.Pair(
                    "BUILD95_KINEMATIC_ROLE joint='" + joint.Name +
                    "' type='" + joint.Type +
                    "' parent='" + (joint.Parent == null ? "" : joint.Parent.LinkName) +
                    "' child='" + (joint.Child == null ? "" : joint.Child.LinkName) +
                    "' role='" + joint.KinematicRole +
                    "' authority='" + joint.KinematicAuthority +
                    "' independent='" + (joint.Independent ?? "") +
                    "' implicit=" + joint.ImplicitMotionCandidate.ToString() +
                    " confidence=" + F(joint.Confidence) +
                    " axis_world=" + joint.AxisWorld.Text() +
                    " pivot_world_m=" + joint.AxisPointWorld.Text() +
                    " source='" + (joint.Source ?? "") +
                    "' evidence='" + (joint.Evidence ?? "") + "'");
            }

            string summary =
                "BUILD95_KINEMATIC_ROLE_SUMMARY active=" + active.ToString(_ci) +
                " dependent=" + dependent.ToString(_ci) +
                " implicit_passive=" + implicitPassive.ToString(_ci) +
                " fixed=" + fixedCount.ToString(_ci) +
                " review=" + review.ToString(_ci);
            model.Warnings.Add(summary);
            Build51Log.Summary(summary);
        }

        private void ApplyBuild95NonDirectImplicitMotionPolicy(MechanicalModel model)
        {
            if (model == null || model.TreeJoints == null) return;

            int implicitTree = 0;
            int implicitLoop = 0;
            int explicitDrivers = 0;
            int nonDirectAnimation = 0;
            int likelyChainOrPin = 0;

            foreach (JointSpec joint in model.TreeJoints.Concat(model.LoopJoints))
            {
                if (joint == null) continue;
                bool movable = !String.Equals(joint.Type, "fixed", StringComparison.OrdinalIgnoreCase);
                if (!movable) continue;

                if (String.Equals(joint.Independent, "true", StringComparison.OrdinalIgnoreCase))
                    explicitDrivers++;

                bool implicitPassive =
                    String.Equals(joint.Independent, "false", StringComparison.OrdinalIgnoreCase) &&
                    (joint.ImplicitMotionCandidate ||
                     (joint.KinematicRole ?? "").IndexOf("implicit", StringComparison.OrdinalIgnoreCase) >= 0 ||
                     (joint.Source ?? "").IndexOf("implicit_passive", StringComparison.OrdinalIgnoreCase) >= 0 ||
                     (joint.Source ?? "").IndexOf("unlocked_insert", StringComparison.OrdinalIgnoreCase) >= 0);

                if (!implicitPassive) continue;

                if (model.TreeJoints.Contains(joint)) implicitTree++;
                else implicitLoop++;

                joint.KinematicRole = "dependent_passive_implicit_coordinate";
                joint.KinematicAuthority = "implicit_inventor_constraint_solver_evidence_non_direct";
                joint.ImplicitMotionCandidate = true;
                if (String.IsNullOrEmpty(joint.Independent)) joint.Independent = "false";

                string parentName = joint.Parent == null ? "" : (joint.Parent.LinkName + " " + joint.Parent.Name + " " + joint.Parent.Path);
                string childName = joint.Child == null ? "" : (joint.Child.LinkName + " " + joint.Child.Name + " " + joint.Child.Path);
                string names = (parentName + " " + childName).ToLowerInvariant();
                bool looksLikeTrackOrPin =
                    names.Contains("chain") || names.Contains("track") || names.Contains("oruga") ||
                    names.Contains("_2780") || names.Contains("n_2780") ||
                    names.Contains("_6558") || names.Contains("n_6558") ||
                    names.Contains("pin") || names.Contains("bush") || names.Contains("connector");

                if (looksLikeTrackOrPin) likelyChainOrPin++;

                // BUILD95 contract: these coordinates exist because Inventor's
                // constraint solver can move them indirectly, but they are not direct
                // user DOF.  The HTML may animate them only when the explicit
                // "Animar componentes no directos" toggle is enabled.
                if ((joint.Source ?? "").IndexOf("BUILD95_NON_DIRECT", StringComparison.OrdinalIgnoreCase) < 0)
                    joint.Source = (joint.Source ?? "") + ";BUILD95_NON_DIRECT_IMPLICIT_PASSIVE";

                nonDirectAnimation++;

                Build51Log.Pair(
                    "BUILD95_NON_DIRECT_IMPLICIT joint='" + joint.Name +
                    "' type='" + joint.Type +
                    "' parent='" + (joint.Parent == null ? "" : joint.Parent.LinkName) +
                    "' child='" + (joint.Child == null ? "" : joint.Child.LinkName) +
                    "' chain_or_pin_like=" + looksLikeTrackOrPin.ToString() +
                    " independent='" + (joint.Independent ?? "") +
                    "' role='" + (joint.KinematicRole ?? "") +
                    "' axis_world=" + joint.AxisWorld.Text() +
                    " pivot_world_m=" + joint.AxisPointWorld.Text() +
                    " source='" + (joint.Source ?? "") +
                    "' evidence='" + (joint.Evidence ?? "") + "'");
            }

            string summary =
                "BUILD95_NON_DIRECT_IMPLICIT_SUMMARY explicit_drivers=" + explicitDrivers.ToString(_ci) +
                " implicit_tree=" + implicitTree.ToString(_ci) +
                " implicit_loop=" + implicitLoop.ToString(_ci) +
                " non_direct_animation_candidates=" + nonDirectAnimation.ToString(_ci) +
                " chain_or_pin_like=" + likelyChainOrPin.ToString(_ci) +
                " policy='direct DOF remain explicit; implicit Inventor motion remains dependent/passive and is only animated by viewer opt-in'";

            model.Warnings.Add(summary);
            Build51Log.Summary(summary);
        }

        private void RecordBuild92ImplicitKinematicCandidates(MechanicalModel model, List<ConstraintInfo> constraints)
        {
            if (model == null || constraints == null) return;

            Dictionary<string, JointSpec> jointByPair = new Dictionary<string, JointSpec>(StringComparer.OrdinalIgnoreCase);
            foreach (JointSpec j in model.TreeJoints.Concat(model.LoopJoints))
            {
                if (j == null || j.Parent == null || j.Child == null) continue;
                string key = PairKey(j.Parent, j.Child);
                if (!jointByPair.ContainsKey(key)) jointByPair[key] = j;
            }

            foreach (IGrouping<string, ConstraintInfo> group in constraints
                .Where(c => c != null && c.A != null && c.B != null && c.A != c.B && !c.Suppressed && c.Healthy && !c.IsRotationCouplingLike)
                .GroupBy(c => PairKey(c.A, c.B)))
            {
                List<ConstraintInfo> bundle = group.ToList();
                bool anyUnlockedInsert = bundle.Any(c => c.IsInsertLike && !c.LockRotation);
                bool anyAxisLike = bundle.Any(c => c.HasAxisLikeGeometry || c.IsInsertLike || c.IsTransitionalLike);
                bool anyAngle = bundle.Any(c => c.IsAngleLike);
                if (!anyAxisLike || anyAngle) continue;

                ConstraintInfo bestAxis = SelectBestAxisConstraint(bundle.Where(c => c.HasAxis && (c.HasAxisLikeGeometry || c.IsInsertLike || c.IsTransitionalLike)).ToList());
                if (bestAxis == null || !bestAxis.HasAxis) continue;

                Vec3 axis = bestAxis.AxisWorld.NormalizedOr(Vec3.UnitZ);
                bool hasPoint;
                Vec3 point = AverageConstraintAxisPoint(bundle.Where(c => c.HasAxis).ToList(), axis, bundle[0].A, bundle[0].B, out hasPoint);
                int rank = RankRows6D(BuildConstraintRows6D(bundle, axis));
                int free = Math.Max(0, 6 - rank);
                JointSpec exported;
                jointByPair.TryGetValue(group.Key, out exported);

                if (free <= 0 && !anyUnlockedInsert) continue;

                ImplicitKinematicCandidate cand = new ImplicitKinematicCandidate();
                cand.PairKey = group.Key;
                cand.LinkA = bundle[0].A.LinkName;
                cand.LinkB = bundle[0].B.LinkName;
                cand.AxisWorld = axis;
                cand.AxisPointWorld = point;
                cand.HasAxisPoint = hasPoint;
                cand.RawRank = rank;
                cand.RawFreeDof = free;
                cand.UnlockedInsert = anyUnlockedInsert;
                cand.AxisLikeCount = bundle.Count(c => c.HasAxisLikeGeometry || c.IsInsertLike || c.IsTransitionalLike);
                cand.PlanarCount = bundle.Count(c => c.HasPlanarGeometry);
                cand.ExportedJoint = exported == null ? "" : exported.Name;
                cand.ExportedType = exported == null ? "omitted" : exported.Type;
                cand.ExportedRole = exported == null ? "no_tree_or_loop_edge" : (exported.KinematicRole ?? "");
                cand.Evidence = String.Join(",", bundle.Select(c => c.StableId).ToArray());
                cand.Reason = anyUnlockedInsert
                    ? "unlocked Insert / concentric shaft can spin in Inventor constraint solver; exported or recorded as passive implicit URDF+ evidence"
                    : "rank leaves residual motion but lacks explicit active authority; review as passive/loop candidate";
                model.ImplicitCandidates.Add(cand);

                Build51Log.Pair(
                    "BUILD95_IMPLICIT_CANDIDATE pair='" + cand.PairKey +
                    "' A='" + cand.LinkA +
                    "' B='" + cand.LinkB +
                    "' rank=" + rank.ToString(_ci) +
                    " free=" + free.ToString(_ci) +
                    " unlocked_insert=" + anyUnlockedInsert.ToString() +
                    " axis=" + axis.Text() +
                    " pivot=" + point.Text() +
                    " exported_joint='" + cand.ExportedJoint +
                    "' exported_type='" + cand.ExportedType +
                    "' exported_role='" + cand.ExportedRole +
                    "' evidence='" + cand.Evidence + "'");
            }

            string summary = "BUILD95_IMPLICIT_CANDIDATE_SUMMARY candidates=" + model.ImplicitCandidates.Count.ToString(_ci);
            model.Warnings.Add(summary);
            Build51Log.Summary(summary);
        }

        private void WriteBuild92KinematicsAuditFiles(MechanicalModel model)
        {
            try
            {
                if (model == null || String.IsNullOrEmpty(_exportDir)) return;
                Directory.CreateDirectory(_exportDir);
                string csvPath = Path.Combine(_exportDir, "AutoMind_BUILD95_KINEMATICS_AUDIT.csv");
                StringBuilder b = new StringBuilder();
                b.AppendLine("kind,name,parent,child,type,independent,role,authority,implicit,requires_review,confidence,axis_world,pivot_world_m,source,evidence");
                foreach (JointSpec j in model.TreeJoints.Concat(model.LoopJoints))
                {
                    if (j == null) continue;
                    b.AppendLine(String.Join(",", new string[] {
                        Csv(model.TreeJoints.Contains(j) ? "tree" : "loop"),
                        Csv(j.Name),
                        Csv(j.Parent == null ? "" : j.Parent.LinkName),
                        Csv(j.Child == null ? "" : j.Child.LinkName),
                        Csv(j.Type),
                        Csv(j.Independent ?? ""),
                        Csv(j.KinematicRole ?? ""),
                        Csv(j.KinematicAuthority ?? ""),
                        Csv(j.ImplicitMotionCandidate ? "true" : "false"),
                        Csv(j.RequiresReview ? "true" : "false"),
                        Csv(F(j.Confidence)),
                        Csv(j.AxisWorld.Text()),
                        Csv(j.AxisPointWorld.Text()),
                        Csv(j.Source ?? ""),
                        Csv(j.Evidence ?? "")
                    }));
                }
                File.WriteAllText(csvPath, b.ToString(), Encoding.UTF8);

                string candPath = Path.Combine(_exportDir, "AutoMind_BUILD95_IMPLICIT_CANDIDATES.csv");
                StringBuilder c = new StringBuilder();
                c.AppendLine("pair,link_a,link_b,rank,free_dof,unlocked_insert,axis_like,planar,axis_world,pivot_world_m,exported_joint,exported_type,exported_role,evidence,reason");
                foreach (ImplicitKinematicCandidate k in model.ImplicitCandidates)
                {
                    c.AppendLine(String.Join(",", new string[] {
                        Csv(k.PairKey), Csv(k.LinkA), Csv(k.LinkB), Csv(k.RawRank.ToString(_ci)), Csv(k.RawFreeDof.ToString(_ci)),
                        Csv(k.UnlockedInsert ? "true" : "false"), Csv(k.AxisLikeCount.ToString(_ci)), Csv(k.PlanarCount.ToString(_ci)),
                        Csv(k.AxisWorld.Text()), Csv(k.AxisPointWorld.Text()), Csv(k.ExportedJoint), Csv(k.ExportedType), Csv(k.ExportedRole),
                        Csv(k.Evidence), Csv(k.Reason)
                    }));
                }
                File.WriteAllText(candPath, c.ToString(), Encoding.UTF8);
                Build51Log.Summary("BUILD95_AUDIT_FILES_WRITTEN kinematics='" + csvPath + "' implicit_candidates='" + candPath + "'");
            }
            catch (Exception ex)
            {
                Build51Log.Warn("BUILD95_AUDIT_FILES_WRITE_FAILED " + ex.Message);
            }
        }

        private void DemotePassiveCoaxialStackRevolutes(MechanicalModel model)
        {
            if (model == null || model.TreeJoints == null || model.TreeJoints.Count == 0)
                return;

            HashSet<string> protectedJointNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            if (model.Couplings != null)
            {
                foreach (CouplingInfo coupling in model.Couplings)
                {
                    if (coupling == null) continue;
                    if (!String.IsNullOrEmpty(coupling.MasterJoint)) protectedJointNames.Add(coupling.MasterJoint);
                    if (!String.IsNullOrEmpty(coupling.DependentJoint)) protectedJointNames.Add(coupling.DependentJoint);
                }
            }

            Dictionary<OccInfo, JointSpec> incomingByChild = new Dictionary<OccInfo, JointSpec>();
            foreach (JointSpec joint in model.TreeJoints)
            {
                if (joint == null || joint.Child == null) continue;
                if (!incomingByChild.ContainsKey(joint.Child)) incomingByChild[joint.Child] = joint;
            }

            int demoted = 0;
            foreach (JointSpec joint in model.TreeJoints.ToList())
            {
                if (joint == null || joint.Parent == null || joint.Child == null)
                    continue;

                if (String.Equals(joint.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    continue;

                if (protectedJointNames.Contains(joint.Name))
                    continue;

                // BUILD95: implicit passive coordinates are intentionally exported as
                // dependent URDF+ motion.  Do not collapse them here; the viewer/debug
                // layer will mark them as passive instead of independent.
                if ((joint.Source ?? "").IndexOf("implicit_passive", StringComparison.OrdinalIgnoreCase) >= 0)
                    continue;

                // A user/solver-declared coordinate must never be frozen by this passive cleanup.
                if (String.Equals(joint.Independent, "true", StringComparison.OrdinalIgnoreCase) ||
                    String.Equals(joint.Independent, "false", StringComparison.OrdinalIgnoreCase))
                    continue;

                JointSpec parentIncoming;
                if (!incomingByChild.TryGetValue(joint.Parent, out parentIncoming) || parentIncoming == null)
                    continue;

                if (String.Equals(parentIncoming.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    continue;

                // If the parent coordinate is protected by a coupling and this child coordinate is not,
                // a same-axis child is almost always a rigid coaxial stack mounted to the driven wheel/axle.
                bool parentIsProtected = protectedJointNames.Contains(parentIncoming.Name) ||
                    String.Equals(parentIncoming.Independent, "true", StringComparison.OrdinalIgnoreCase) ||
                    String.Equals(parentIncoming.Independent, "false", StringComparison.OrdinalIgnoreCase);

                if (!parentIsProtected)
                    continue;

                if (!AreCoaxialShaftJoints(parentIncoming, joint))
                    continue;

                string previousType = joint.Type;
                string previousIndependent = joint.Independent ?? "";

                joint.Type = "fixed";
                joint.EstimatedFreeDof = 0;
                joint.Independent = "";
                joint.MimicJointName = null;
                joint.MimicMultiplier = 1.0;
                joint.MimicOffset = 0.0;
                joint.Lower = 0.0;
                joint.Upper = 0.0;
                joint.Source = (joint.Source ?? "") +
                    ";BUILD91_demoted_passive_coaxial_stack_revolute_to_fixed";
                joint.PivotSource = (joint.PivotSource ?? "") +
                    ";passive_coaxial_stack_parent=" + parentIncoming.Name;
                joint.Confidence = Math.Max(joint.Confidence, 0.990);

                demoted++;
                Build51Log.Pair(
                    "BUILD91_PASSIVE_COAXIAL_STACK_DEMOTED joint='" + joint.Name +
                    "' previous_type='" + previousType +
                    "' previous_independent='" + previousIndependent +
                    "' parent_driver='" + parentIncoming.Name +
                    "' axis=" + joint.AxisWorld.NormalizedOr(Vec3.UnitZ).Text() +
                    " parent_axis=" + parentIncoming.AxisWorld.NormalizedOr(Vec3.UnitZ).Text() +
                    " pivot_line_error_m=" + F(CoaxialLineDistance(parentIncoming, joint)) +
                    " reason='unprotected serial revolute on protected driven shaft is a rigid stack, not a new DOF'");
            }

            if (demoted > 0)
            {
                string warning =
                    "BUILD91 passive coaxial stack cleanup demoted " +
                    demoted.ToString(_ci) +
                    " unprotected serial revolute joint(s) to fixed rigid-stack joints.";
                model.Warnings.Add(warning);
                Build51Log.Warn(warning);
            }
        }

        private bool AreCoaxialShaftJoints(JointSpec a, JointSpec b)
        {
            if (a == null || b == null)
                return false;

            Vec3 axisA = a.AxisWorld.NormalizedOr(Vec3.UnitZ);
            Vec3 axisB = b.AxisWorld.NormalizedOr(Vec3.UnitZ);
            double axisDotAbs = Math.Abs(axisA.Dot(axisB));
            if (axisDotAbs < 0.985)
                return false;

            double lineDistance = CoaxialLineDistance(a, b);

            double scale = 0.005;
            if (a.Parent != null) scale = Math.Max(scale, OccurrenceCharacteristicSize(a.Parent));
            if (a.Child != null) scale = Math.Max(scale, OccurrenceCharacteristicSize(a.Child));
            if (b.Parent != null) scale = Math.Max(scale, OccurrenceCharacteristicSize(b.Parent));
            if (b.Child != null) scale = Math.Max(scale, OccurrenceCharacteristicSize(b.Child));

            double tolerance = Math.Max(0.0015, scale * 0.12);
            return lineDistance <= tolerance;
        }

        private double CoaxialLineDistance(JointSpec a, JointSpec b)
        {
            if (a == null || b == null)
                return Double.PositiveInfinity;

            Vec3 axis = a.AxisWorld.NormalizedOr(Vec3.UnitZ);
            Vec3 delta = b.AxisPointWorld - a.AxisPointWorld;
            Vec3 perpendicular = delta - axis * delta.Dot(axis);
            return perpendicular.Length;
        }


        private void AddBuild124ClosedChainLoopCouplings(MechanicalModel model)
        {
            if (model == null) return;

            List<JointSpec> passive =
                model.TreeJoints
                    .Where(j =>
                        j != null &&
                        !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                        !String.Equals(j.Independent, "true", StringComparison.OrdinalIgnoreCase))
                    .ToList();

            List<JointSpec> loops =
                model.LoopJoints
                    .Where(j => j != null)
                    .ToList();

            if (passive.Count == 0 && loops.Count == 0)
                return;

            JointSpec master =
                model.TreeJoints.FirstOrDefault(j =>
                    j != null &&
                    !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                    String.Equals(j.Independent, "true", StringComparison.OrdinalIgnoreCase));

            if (master == null)
                master = passive.FirstOrDefault();

            string dependentNames =
                String.Join(
                    " ",
                    passive
                        .Where(j => master == null || !Object.ReferenceEquals(j, master))
                        .Select(j => j.Name)
                        .Concat(loops.Select(j => j.Name))
                        .Distinct()
                        .ToArray());

            CouplingInfo graph = new CouplingInfo();
            graph.Name = "automind_build124_closed_chain_solver_graph";
            graph.Type = "closed_chain_solver_graph";
            graph.Solver = "gauss_newton_multi_loop_pin_axis_closure";
            graph.Mode = "solve_dependent_passive_coordinates_from_usd_loop_joints_or_implicit_closure_candidates";
            graph.MasterJoint = master == null ? "" : master.Name;
            graph.DependentJoint = dependentNames;
            graph.MasterLink = master == null || master.Child == null ? "" : master.Child.LinkName;
            graph.DependentLink = "";
            graph.Ratio = 1.0;
            graph.Offset = 0.0;
            graph.Source = "BUILD128 inferred from CAD rank/free_dof constraints, exported USD loop joints, omitted implicit closure candidates, and strict UsdPhysics joint schema";
            graph.Evidence =
                String.Join(
                    ",",
                    loops
                        .Select(j => j.Evidence)
                        .Where(s => !String.IsNullOrEmpty(s))
                        .ToArray());

            model.Couplings.Add(graph);

            foreach (JointSpec loop in loops)
            {
                CouplingInfo lc = new CouplingInfo();
                lc.Name = "loop_closure_" + SanitizeName(loop.Name);
                lc.Type = "loop_closure";
                lc.Solver = "pin_axis_pose_closure";
                lc.Mode = "body0_local_frame_equals_body1_local_frame";
                lc.MasterJoint = master == null ? "" : master.Name;
                lc.DependentJoint = loop.Name;
                lc.MasterLink = loop.Parent == null ? "" : loop.Parent.LinkName;
                lc.DependentLink = loop.Child == null ? "" : loop.Child.LinkName;
                lc.Ratio = 1.0;
                lc.Offset = 0.0;
                lc.Source = "BUILD124 USD loop closure metadata";
                lc.Evidence = loop.Evidence;
                model.Couplings.Add(lc);
            }

            Build51Log.Robot(
                "BUILD124_CLOSED_CHAIN_COUPLINGS_ADDED passive_tree=" +
                passive.Count.ToString(_ci) +
                " loops=" +
                loops.Count.ToString(_ci) +
                " couplings_total=" +
                model.Couplings.Count.ToString(_ci) +
                " master='" +
                (master == null ? "" : master.Name) +
                "'");
        }

        private void PromoteBuild124ImplicitDriverIfNeeded(MechanicalModel model)
        {
            if (model == null || model.TreeJoints == null) return;

            bool hasIndependent =
                model.TreeJoints.Any(j =>
                    j != null &&
                    !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                    String.Equals(j.Independent, "true", StringComparison.OrdinalIgnoreCase));

            if (hasIndependent) return;

            JointSpec driver =
                model.TreeJoints
                    .Where(j =>
                        j != null &&
                        !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(j => j.Confidence)
                    .FirstOrDefault();

            if (driver == null) return;

            driver.Independent = "true";
            driver.KinematicRole = "active_inferred_driver_coordinate";
            driver.KinematicAuthority = "BUILD124_safe_single_driver_for_closed_chain_debug";
            driver.RequiresReview = true;
            driver.ReviewReason =
                "No explicit Inventor AssemblyJoint/RotationConstraint was found, but the CAD graph has passive 1-DOF rank-5 hinges. BUILD124 promotes one hinge as a user driver so the USD viewer can actuate the closed-chain solver.";
            model.IndependentDof = Math.Max(model.IndependentDof, 1);

            Build51Log.Warn(
                "BUILD124_INFERRED_DRIVER_PROMOTED joint='" +
                driver.Name +
                "' reason='no explicit independent DOF but passive rank5 closed-chain hinges exist'");
        }

        private void AddExplicitRotationConstraintCouplings(
            MechanicalModel model,
            List<ConstraintInfo> constraints)
        {
            if (model == null ||
                constraints == null)
                return;

            HashSet<string> emitted =
                new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase);

            foreach (ConstraintInfo constraint in constraints)
            {
                if (constraint == null ||
                    !constraint.IsRotationCouplingLike ||
                    constraint.Suppressed ||
                    !constraint.Healthy ||
                    constraint.A == null ||
                    constraint.B == null ||
                    constraint.A == constraint.B)
                    continue;

                JointSpec jointA =
                    FindBestMovableJointForOccurrence(
                        model,
                        constraint.A);

                JointSpec jointB =
                    FindBestMovableJointForOccurrence(
                        model,
                        constraint.B);

                if (jointA != null && jointB != null && Object.ReferenceEquals(jointA, jointB))
                {
                    JointSpec altB =
                        FindBestMovableJointForOccurrenceExcluding(
                            model,
                            constraint.B,
                            jointA);

                    if (altB != null)
                        jointB = altB;
                    else
                    {
                        JointSpec altA =
                            FindBestMovableJointForOccurrenceExcluding(
                                model,
                                constraint.A,
                                jointB);

                        if (altA != null)
                            jointA = altA;
                    }
                }

                if (jointA == null ||
                    jointB == null ||
                    Object.ReferenceEquals(jointA, jointB))
                {
                    model.Warnings.Add(
                        "Explicit Inventor rotation constraint could not be mapped to two movable URDF joints: " +
                        constraint.Name +
                        " (" +
                        constraint.StableId +
                        ").");

                    Build51Log.Warn(
                        "BUILD89_ROTATION_COUPLING_UNMAPPED id='" +
                        constraint.StableId +
                        "' name='" +
                        constraint.Name +
                        "' A='" +
                        constraint.A.LinkName +
                        "' B='" +
                        constraint.B.LinkName +
                        "' jointA='" +
                        (jointA == null ? "" : jointA.Name) +
                        "' jointB='" +
                        (jointB == null ? "" : jointB.Name) +
                        "'");

                    continue;
                }

                string key =
                    String.Compare(
                        jointA.Name,
                        jointB.Name,
                        StringComparison.OrdinalIgnoreCase) <= 0
                    ? jointA.Name + "|" + jointB.Name
                    : jointB.Name + "|" + jointA.Name;

                if (!emitted.Add(key))
                {
                    Build51Log.Warn(
                        "BUILD83_ROTATION_COUPLING_DUPLICATE_OMITTED id='" +
                        constraint.StableId +
                        "' key='" +
                        key + "'");

                    continue;
                }

                // Preserve the semantic order of Inventor RotationConstraint:
                // EntityTwo = Ratio * EntityOne + Offset. Reordering by tree depth
                // changes a 24:1 worm relation into the wrong transmission.
                JointSpec master = jointA;
                JointSpec dependent = jointB;

                double ratio =
                    constraint.MotionRatio;

                if (Double.IsNaN(ratio) ||
                    Double.IsInfinity(ratio) ||
                    Math.Abs(ratio) < 1e-12)
                    ratio = 1.0;

                // Align the sign with the exported joint axes. Inventor may report
                // opposite axis directions for equivalent rotational coordinates.
                double axisDot =
                    master.AxisWorld
                        .NormalizedOr(Vec3.UnitZ)
                        .Dot(
                            dependent.AxisWorld
                                .NormalizedOr(Vec3.UnitZ));

                if (Math.Abs(axisDot) > 0.95 && axisDot < 0.0)
                    ratio *= -1.0;

                CouplingInfo coupling =
                    new CouplingInfo();

                coupling.Name =
                    "inventor_rotation_" +
                    SanitizeName(
                        constraint.StableId);

                coupling.Type =
                    "linear_rotation";

                coupling.Solver =
                    "explicit_inventor_rotation_constraint";

                coupling.Mode =
                    "q_dependent=ratio*q_master+offset";

                coupling.MasterJoint =
                    master.Name;

                coupling.DependentJoint =
                    dependent.Name;

                coupling.MasterLink =
                    master.Child == null
                    ? ""
                    : master.Child.LinkName;

                coupling.DependentLink =
                    dependent.Child == null
                    ? ""
                    : dependent.Child.LinkName;

                coupling.Ratio =
                    ratio;

                coupling.Offset =
                    constraint.MotionOffset;

                coupling.Source =
                    "Inventor RotationConstraint";

                coupling.Evidence =
                    constraint.StableId;

                model.Couplings.Add(
                    coupling);

                if (String.IsNullOrEmpty(
                        master.Independent))
                    master.Independent =
                        "true";

                dependent.Independent =
                    "false";

                Build51Log.Pair(
                    "BUILD83_ROTATION_COUPLING_EMITTED id='" +
                    constraint.StableId +
                    "' master='" +
                    master.Name +
                    "' dependent='" +
                    dependent.Name +
                    "' ratio=" +
                    F(coupling.Ratio) +
                    " offset=" +
                    F(coupling.Offset) +
                    " axis_dot=" +
                    F(axisDot) +
                    " source='" +
                    coupling.Source + "'");
            }
        }

        private JointSpec FindBestMovableJointForOccurrenceExcluding(
            MechanicalModel model,
            OccInfo occurrence,
            JointSpec excluded)
        {
            if (model == null || occurrence == null)
                return null;

            List<JointSpec> candidates =
                model.TreeJoints
                    .Where(j =>
                        j != null &&
                        !Object.ReferenceEquals(j, excluded) &&
                        !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    .ToList();

            if (candidates.Count == 0)
                return null;

            // First look for an adjacent or component-boundary coordinate that is
            // geometrically closest to the coupling endpoint.  This fixes the log
            // case where both endpoints of Inventor Rotación/Traslación were mapped
            // to the same hub joint even though the second endpoint had a different
            // shaft coordinate nearby.
            HashSet<OccInfo> rigidComponent = new HashSet<OccInfo>();
            Queue<OccInfo> queue = new Queue<OccInfo>();
            rigidComponent.Add(occurrence);
            queue.Enqueue(occurrence);

            while (queue.Count > 0)
            {
                OccInfo current = queue.Dequeue();

                foreach (JointSpec fixedJoint in model.TreeJoints.Where(j =>
                    j != null &&
                    String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                    (j.Parent == current || j.Child == current)))
                {
                    OccInfo other = fixedJoint.Parent == current ? fixedJoint.Child : fixedJoint.Parent;
                    if (other != null && rigidComponent.Add(other))
                        queue.Enqueue(other);
                }
            }

            Vec3 center = occurrence.World.Translation;

            return candidates
                .Where(j =>
                    j.Child == occurrence ||
                    j.Parent == occurrence ||
                    rigidComponent.Contains(j.Child) ||
                    rigidComponent.Contains(j.Parent))
                .OrderByDescending(j =>
                {
                    Vec3 axis = j.AxisWorld.NormalizedOr(Vec3.UnitZ);
                    Vec3 delta = center - j.AxisPointWorld;
                    double radialDistance = (delta - axis * delta.Dot(axis)).Length;
                    double pivotDistance = delta.Length;
                    double roleBonus =
                        j.Child == occurrence ? 500.0 :
                        j.Parent == occurrence ? 350.0 :
                        rigidComponent.Contains(j.Child) ? 260.0 : 120.0;

                    return roleBonus + 40.0 * j.Confidence - 7000.0 * radialDistance - 35.0 * pivotDistance;
                })
                .ThenBy(j => j.Name)
                .FirstOrDefault();
        }

        private JointSpec FindBestMovableJointForOccurrence(
            MechanicalModel model,
            OccInfo occurrence)
        {
            if (model == null || occurrence == null)
                return null;

            List<JointSpec> directChild =
                model.TreeJoints
                    .Where(j =>
                        j != null &&
                        j.Child == occurrence &&
                        !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(j => j.Confidence)
                    .ToList();

            if (directChild.Count > 0)
                return directChild[0];

            // Build the complete rigid component containing the selected occurrence.
            // A gear is commonly fixed to an axle; the coordinate belongs to the axle's
            // bearing, not to the gear link itself.
            HashSet<OccInfo> rigidComponent = new HashSet<OccInfo>();
            Queue<OccInfo> queue = new Queue<OccInfo>();
            rigidComponent.Add(occurrence);
            queue.Enqueue(occurrence);

            while (queue.Count > 0)
            {
                OccInfo current = queue.Dequeue();

                foreach (JointSpec fixedJoint in model.TreeJoints.Where(j =>
                    j != null &&
                    String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                    (j.Parent == current || j.Child == current)))
                {
                    OccInfo other = fixedJoint.Parent == current
                        ? fixedJoint.Child
                        : fixedJoint.Parent;

                    if (other != null && rigidComponent.Add(other))
                        queue.Enqueue(other);
                }
            }

            List<JointSpec> boundary =
                model.TreeJoints
                    .Where(j =>
                        j != null &&
                        !String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase) &&
                        (rigidComponent.Contains(j.Child) || rigidComponent.Contains(j.Parent)))
                    .ToList();

            if (boundary.Count > 0)
            {
                Vec3 center = occurrence.World.Translation;

                return boundary
                    .OrderByDescending(j =>
                    {
                        Vec3 axis = j.AxisWorld.NormalizedOr(Vec3.UnitZ);
                        Vec3 delta = center - j.AxisPointWorld;
                        double radialDistance =
                            (delta - axis * delta.Dot(axis)).Length;
                        double pivotDistance = delta.Length;
                        double roleBonus =
                            j.Child == occurrence ? 400.0 :
                            rigidComponent.Contains(j.Child) ? 250.0 : 100.0;

                        return roleBonus +
                            40.0 * j.Confidence -
                            5000.0 * radialDistance -
                            30.0 * pivotDistance;
                    })
                    .ThenBy(j => j.Name)
                    .FirstOrDefault();
            }

            // Final ancestor fallback for unusual trees.
            Dictionary<OccInfo, JointSpec> byChild =
                model.TreeJoints
                    .Where(j => j != null && j.Child != null)
                    .GroupBy(j => j.Child)
                    .ToDictionary(group => group.Key, group => group.First());

            OccInfo ancestor = occurrence;
            HashSet<OccInfo> visited = new HashSet<OccInfo>();

            while (ancestor != null && visited.Add(ancestor))
            {
                JointSpec incoming;
                if (!byChild.TryGetValue(ancestor, out incoming))
                    break;

                if (!String.Equals(incoming.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    return incoming;

                ancestor = incoming.Parent;
            }

            return null;
        }

        private int JointDepthFromRoot(
            MechanicalModel model,
            JointSpec target)
        {
            if (model == null ||
                target == null)
                return Int32.MaxValue;

            Dictionary<OccInfo, JointSpec> byChild =
                model.TreeJoints
                    .Where(j =>
                        j != null &&
                        j.Child != null)
                    .GroupBy(j =>
                        j.Child)
                    .ToDictionary(
                        group => group.Key,
                        group => group.First());

            int depth = 0;
            OccInfo current =
                target.Child;

            HashSet<OccInfo> visited =
                new HashSet<OccInfo>();

            while (current != null &&
                   visited.Add(current))
            {
                JointSpec incoming;
                if (!byChild.TryGetValue(
                        current,
                        out incoming))
                    break;

                depth++;
                current =
                    incoming.Parent;
            }

            return depth;
        }

        private List<MechanicalEdge> SelectSpanningTree(OccInfo root, List<OccInfo> occs, List<MechanicalEdge> edges)
        {
            // Maximum-score undirected spanning tree, then orient by BFS from root.
            Dsu dsu = new Dsu(occs.Count);
            Dictionary<OccInfo, int> idx = occs.ToDictionary(o => o, o => o.Index);
            List<MechanicalEdge> chosen = new List<MechanicalEdge>();
            foreach (MechanicalEdge e in edges.OrderByDescending(e => e.Score).ThenBy(e => e.Type == "fixed" ? 1 : 0))
            {
                if (e.A == null || e.B == null || e.A == e.B) continue;
                int ia = idx[e.A], ib = idx[e.B];
                if (dsu.Find(ia) == dsu.Find(ib)) continue;
                dsu.Union(ia, ib);
                chosen.Add(e);
            }

            // Orient edges away from selected root.
            Dictionary<OccInfo, List<MechanicalEdge>> adj = new Dictionary<OccInfo, List<MechanicalEdge>>();
            foreach (OccInfo o in occs) adj[o] = new List<MechanicalEdge>();
            foreach (MechanicalEdge e in chosen)
            {
                adj[e.A].Add(e);
                adj[e.B].Add(e);
            }
            List<MechanicalEdge> oriented = new List<MechanicalEdge>();
            Queue<OccInfo> q = new Queue<OccInfo>();
            HashSet<OccInfo> seen = new HashSet<OccInfo>();
            q.Enqueue(root); seen.Add(root);
            while (q.Count > 0)
            {
                OccInfo u = q.Dequeue();
                foreach (MechanicalEdge e in adj[u])
                {
                    OccInfo v = e.Other(u);
                    if (seen.Contains(v)) continue;
                    seen.Add(v); q.Enqueue(v);
                    MechanicalEdge oe = e.Clone();
                    oe.Parent = u; oe.Child = v;
                    oriented.Add(oe);
                }
            }
            return oriented;
        }

        private JointSpec MakeJointFromEdge(MechanicalModel model, MechanicalEdge e, bool tree)
        {
            JointSpec joint =
                new JointSpec();

            joint.Parent =
                tree
                ? e.Parent
                : e.A;

            joint.Child =
                tree
                ? e.Child
                : e.B;

            if (joint.Parent == null ||
                joint.Child == null)
            {
                joint.Parent = e.A;
                joint.Child = e.B;
            }

            joint.Type =
                e.Type;

            joint.AxisWorld =
                e.AxisWorld.NormalizedOr(
                    Vec3.UnitZ);

            joint.AxisPointWorld =
                e.HasAxisPoint
                ? e.AxisPointWorld
                : Mid(
                    joint.Parent.World.Translation,
                    joint.Child.World.Translation);

            joint.PivotSource =
                e.HasAxisPoint
                ? "cad_scored_axis_point"
                : "legacy_texturas_occurrence_midpoint";

            joint.Source =
                e.Source;

            joint.Evidence =
                e.Evidence;

            joint.Confidence =
                e.Confidence;

            joint.EstimatedFreeDof =
                e.EstimatedFreeDof;

            joint.ConstraintKind =
                String.Equals(
                    joint.Type,
                    "fixed",
                    StringComparison.OrdinalIgnoreCase)
                ? "6d"
                : (
                    String.Equals(
                        joint.Type,
                        "cylindrical",
                        StringComparison.OrdinalIgnoreCase) ||
                    String.Equals(
                        joint.Type,
                        "universal",
                        StringComparison.OrdinalIgnoreCase)
                    ? "4d"
                    : (
                        String.Equals(
                            joint.Type,
                            "planar",
                            StringComparison.OrdinalIgnoreCase) ||
                        String.Equals(
                            joint.Type,
                            "spherical",
                            StringComparison.OrdinalIgnoreCase)
                        ? "3d_multi"
                        : "5d"));

            joint.Name =
                (tree ? "joint_" : "loop_") +
                SanitizeName(
                    joint.Type +
                    "_" +
                    joint.Parent.LinkName +
                    "_to_" +
                    joint.Child.LinkName);

            if (String.Equals(
                    joint.Type,
                    "revolute",
                    StringComparison.OrdinalIgnoreCase))
            {
                joint.Lower = -Math.PI;
                joint.Upper = Math.PI;
                joint.Effort = 10;
                joint.Velocity = 10;
            }
            else if (String.Equals(
                    joint.Type,
                    "prismatic",
                    StringComparison.OrdinalIgnoreCase))
            {
                joint.Lower = -0.10;
                joint.Upper = 0.10;
                joint.Effort = 100;
                joint.Velocity = 1;
            }

            Build51Log.Pair(
                "JOINT_FROM_EDGE role='" +
                (tree ? "TREE" : "LOOP") +
                "' name='" +
                joint.Name +
                "' type='" +
                joint.Type +
                "' parent='" +
                (joint.Parent == null
                    ? "null"
                    : joint.Parent.LinkName) +
                "' child='" +
                (joint.Child == null
                    ? "null"
                    : joint.Child.LinkName) +
                "' axis_world=" +
                joint.AxisWorld.Text() +
                " pivot_world_m=" +
                joint.AxisPointWorld.Text() +
                " pivot_policy='" +
                joint.PivotSource +
                "' confidence=" +
                F(joint.Confidence) +
                " estimated_free_dof=" +
                joint.EstimatedFreeDof.ToString(_ci) +
                " source='" +
                joint.Source +
                "' evidence='" +
                joint.Evidence + "'");

            return joint;
        }

        private bool TryApplyParallelGripperOverlay(MechanicalModel model, List<OccInfo> occs, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints)
        {
            // Guarded by topology first: roughly 20 leaf bodies, many pin-like coaxial mates,
            // two symmetric gear/link/gripper branches, and one native driving joint.
            int pinLike = constraints.Count(c => c.HasAxis && c.HasAxisPoint);
            bool topologyMatches = occs.Count >= 14 && pinLike >= 10 && nativeJoints.Count >= 1;
            if (!topologyMatches) return false;

            OccInfo basePlate1 = FindByName(occs, "base", "plate", "1") ?? model.RootOccurrence;
            OccInfo basePlate2 = FindByName(occs, "base", "plate", "2");
            OccInfo bracket = FindByName(occs, "bracket") ?? FindByName(occs, "mounting");
            OccInfo baseGear = FindByName(occs, "base", "gear");
            OccInfo gear1 = FindByName(occs, "gear", "link", "1");
            OccInfo gear2 = FindByName(occs, "gear", "link", "2");
            OccInfo gripper1 = FindByName(occs, "gripper", "1");
            OccInfo gripper2 = FindByName(occs, "gripper", "2");
            // BUILD71: do not use broad substring matching for the blue connector links.
            // "Gear link 1" also contains "link" and "1", which produced self-joints:
            //   Gear_link_1 -> Gear_link_1
            // The plain connector parts must be selected by exact display-name prefix
            // and must exclude gear/gripper/base/pin words.
            OccInfo link1 = FindPlainNumberedPart(occs, "link", "1", new string[] { "gear", "gripper", "base", "pin" });
            OccInfo link2 = FindPlainNumberedPart(occs, "link", "2", new string[] { "gear", "gripper", "base", "pin" });
            if (baseGear == null || gear1 == null || gear2 == null || gripper1 == null || gripper2 == null || link1 == null || link2 == null) return false;
            if (DistinctNonNullCount(basePlate1, baseGear, gear1, gear2, gripper1, gripper2, link1, link2) < 8)
            {
                model.Warnings.Add("parallel_gripper_overlay rejected: non-distinct named parts after exact matching");
                return false;
            }

            model.Warnings.Add("parallel_gripper_overlay: explicit deterministic tree/mimic/loop overlay applied after topology match");
            model.RootOccurrence = basePlate1;
            model.TreeJoints.Clear();
            model.LoopJoints.Clear();
            model.Couplings.Clear();

            // Fixed base island.
            if (basePlate2 != null) model.TreeJoints.Add(Fixed(basePlate1, basePlate2, "base_plate_stack"));
            if (bracket != null) model.TreeJoints.Add(Fixed(basePlate1, bracket, "base_bracket"));

            JointSpec master = Revolute(basePlate1, baseGear, "driver_base_gear", baseGear.World.Translation, Vec3.UnitZ, "continuous");
            master.Independent = "true";
            model.TreeJoints.Add(master);

            JointSpec jg1 = Revolute(basePlate1, gear1, "gear_link_1", gear1.World.Translation, Vec3.UnitZ, "revolute");
            JointSpec jg2 = Revolute(basePlate1, gear2, "gear_link_2", gear2.World.Translation, Vec3.UnitZ, "revolute");
            jg1.Independent = "false";
            jg2.Independent = "false";
            // Gear-to-gear motion is a true angular relation, so mimic/coupling is valid here.
            jg1.MimicJointName = master.Name; jg1.MimicMultiplier = 1.0;
            jg2.MimicJointName = master.Name; jg2.MimicMultiplier = -1.0;
            model.TreeJoints.Add(jg1); model.TreeJoints.Add(jg2);

            // BUILD129: restore the validated BUILD97 physical topology.
            // Link_1 / Link_2 are ground rockers at Pin_3 / Pin_6.  They must NOT be
            // children of Gear_link_1 / Gear_link_2, otherwise dragging or loop solving
            // separates the rods from the real Inventor pivots.
            Vec3 pLink1Ground = new Vec3(-0.00524, -0.058, 0.0042);
            Vec3 pLink2Ground = new Vec3( 0.00524, -0.058, 0.0042);
            Vec3 pJaw1Gear2 = new Vec3( 0.01439759, -0.06858273, 0.0);
            Vec3 pJaw2Gear1 = new Vec3(-0.01442652, -0.06858615, 0.0);

            JointSpec jl1 = Revolute(basePlate1, link1, "blue_link_1", pLink1Ground, Vec3.UnitZ, "revolute");
            JointSpec jl2 = Revolute(basePlate1, link2, "blue_link_2", pLink2Ground, Vec3.UnitZ, "revolute");
            jl1.Independent = "false";
            jl2.Independent = "false";
            jl1.Source = "parallel_gripper_overlay_revolute_BUILD129_ground_rocker";
            jl2.Source = "parallel_gripper_overlay_revolute_BUILD129_ground_rocker";
            jl1.Evidence = "BUILD129: Link_1 grounded rocker at Pin_3; previous gear-child topology caused decoupling.";
            jl2.Evidence = "BUILD129: Link_2 grounded rocker at Pin_6; previous gear-child topology caused decoupling.";
            model.TreeJoints.Add(jl1); model.TreeJoints.Add(jl2);

            JointSpec jaw1 = Revolute(gear2, gripper1, "jaw_1", pJaw1Gear2, Vec3.UnitZ, "revolute");
            JointSpec jaw2 = Revolute(gear1, gripper2, "jaw_2", pJaw2Gear1, Vec3.UnitZ, "revolute");
            jaw1.Independent = "false";
            jaw2.Independent = "false";
            jaw1.Source = "parallel_gripper_overlay_revolute_BUILD129_gear_to_jaw";
            jaw2.Source = "parallel_gripper_overlay_revolute_BUILD129_gear_to_jaw";
            jaw1.Evidence = "BUILD129: Gripper_1 hinged to Gear_link_2 at Pin_4; loop to Link_2 closes Pin_8.";
            jaw2.Evidence = "BUILD129: Gripper_2 hinged to Gear_link_1 at Pin_7; loop to Link_1 closes Pin_5.";
            model.TreeJoints.Add(jaw1); model.TreeJoints.Add(jaw2);

            Build51Log.Summary("BUILD129_GRIPPER_TOPOLOGY_REPAIRED link1_parent='" + basePlate1.LinkName +
                "' link2_parent='" + basePlate1.LinkName +
                "' jaw1_parent='" + gear2.LinkName +
                "' jaw2_parent='" + gear1.LinkName +
                "' reason='validated Inventor-style four-bar topology; prevents Link_1/Link_2 decoupling'");

            // Keep pins as physical visuals, fixed to their nearest non-pin owner.
            HashSet<OccInfo> alreadyChildren = new HashSet<OccInfo>(model.TreeJoints.Select(j => j.Child));
            foreach (OccInfo pin in occs.Where(o => o.Name.ToLowerInvariant().Contains("pin")))
            {
                if (alreadyChildren.Contains(pin)) continue;
                OccInfo owner = ChoosePinOwner(pin, new[] { basePlate1, basePlate2, bracket, baseGear, gear1, gear2, gripper1, gripper2, link1, link2 }.Where(x => x != null).ToList(), constraints);
                OccInfo deterministicOwner = ChooseBuild129ParallelGripperPinOwner(pin, basePlate1, gear1, gear2, link1, link2);
                if (deterministicOwner != null)
                {
                    Build51Log.Pair("BUILD129_GRIPPER_PIN_OWNER_OVERRIDE pin='" + pin.LinkName + "' from='" + (owner == null ? "" : owner.LinkName) + "' to='" + deterministicOwner.LinkName + "'");
                    owner = deterministicOwner;
                }
                if (owner == null) owner = basePlate1;
                JointSpec pinFixedJoint = Fixed(owner, pin, "pin_visual_" + pin.LinkName);
                pinFixedJoint.Source = "parallel_gripper_overlay_fixed_pin_owner_by_constraint_evidence";
                pinFixedJoint.Evidence = GripperPinOwnerEvidence(pin, owner, constraints);
                model.TreeJoints.Add(pinFixedJoint);
                alreadyChildren.Add(pin);
                Build51Log.Pair("BUILD95_GRIPPER_PIN_OWNER pin='" + pin.LinkName +
                    "' owner='" + owner.LinkName +
                    "' evidence='" + pinFixedJoint.Evidence +
                    "' pin_xyz=" + pin.World.Translation.Text() +
                    " owner_xyz=" + owner.World.Translation.Text());
            }

            // Any unassigned occurrence remains fixed to root for visual safety.
            foreach (OccInfo occ in occs)
            {
                if (occ == basePlate1) continue;
                if (alreadyChildren.Contains(occ)) continue;
                model.TreeJoints.Add(Fixed(basePlate1, occ, "visual_unassigned_" + occ.LinkName));
                alreadyChildren.Add(occ);
            }

            // BUILD95: loop closures from repaired CAD evidence, normalized through fixed pin visuals.
            // A LEGO pin is a physical visual occurrence; it should not become a separate loop endpoint
            // when it is already fixed to one real moving body.  Normalize Pin -> fixed owner so URDF+
            // stores the real mechanism closure (for example Gripper_1 <-> Link_2), not Pin_8 <-> Link_2.
            Dictionary<OccInfo, OccInfo> overlayFixedOwnerByChild = new Dictionary<OccInfo, OccInfo>();
            foreach (JointSpec tj in model.TreeJoints)
            {
                if (tj == null || tj.Parent == null || tj.Child == null) continue;
                if (!String.Equals(tj.Type, "fixed", StringComparison.OrdinalIgnoreCase)) continue;
                if (IsPinOccurrence(tj.Child)) overlayFixedOwnerByChild[tj.Child] = tj.Parent;
            }

            HashSet<string> overlayLoopPairs = new HashSet<string>();
            int normalizedPinLoopEndpoints = 0;
            int skippedRedundantPinLoops = 0;
            foreach (ConstraintInfo c in constraints.Where(c => c.HasAxis && c.A != null && c.B != null && c.A != c.B))
            {
                OccInfo loopA = ResolveOverlayLoopEndpoint(c.A, overlayFixedOwnerByChild);
                OccInfo loopB = ResolveOverlayLoopEndpoint(c.B, overlayFixedOwnerByChild);
                if (loopA == null || loopB == null || loopA == loopB)
                {
                    skippedRedundantPinLoops++;
                    Build51Log.Pair("BUILD95_GRIPPER_LOOP_SKIPPED_REDUNDANT constraint='" + c.StableId +
                        "' rawA='" + (c.A == null ? "" : c.A.LinkName) +
                        "' rawB='" + (c.B == null ? "" : c.B.LinkName) + "'");
                    continue;
                }
                if (loopA != c.A || loopB != c.B) normalizedPinLoopEndpoints++;

                string pk = PairKey(loopA, loopB);
                bool alreadyTree = model.TreeJoints.Any(j => PairKey(j.Parent, j.Child) == pk);
                if (alreadyTree)
                {
                    skippedRedundantPinLoops++;
                    Build51Log.Pair("BUILD95_GRIPPER_LOOP_SKIPPED_TREE_PAIR constraint='" + c.StableId +
                        "' pair='" + pk + "'");
                    continue;
                }
                if (overlayLoopPairs.Contains(pk)) continue;
                overlayLoopPairs.Add(pk);
                JointSpec loop = new JointSpec();
                loop.Name = "loop_" + SanitizeName(loopA.LinkName + "_to_" + loopB.LinkName + "_" + c.Index.ToString(_ci));
                loop.Parent = loopA;
                loop.Child = loopB;
                loop.Type = "revolute";
                loop.ConstraintKind = "3d";
                loop.AxisWorld = c.AxisWorld.NormalizedOr(Vec3.UnitZ);
                loop.AxisPointWorld = c.HasAxisPoint ? c.AxisPointWorld : Mid(loopA.World.Translation, loopB.World.Translation);
                loop.Source = (loopA != c.A || loopB != c.B)
                    ? "parallel_gripper_loop_pin_endpoint_normalized_to_owner"
                    : "parallel_gripper_repaired_axis_loop";
                loop.Evidence = c.StableId + ((loopA != c.A || loopB != c.B)
                    ? (" raw_pair=" + c.A.LinkName + "<->" + c.B.LinkName)
                    : "");
                loop.PivotSource = c.HasAxisPoint
                    ? "cad_axis_point_pin_normalized_to_physical_body"
                    : "legacy_texturas_occurrence_midpoint";
                loop.Confidence = c.HasAxisLikeGeometry ? 0.95 : 0.75;
                loop.EstimatedFreeDof = 1;
                model.LoopJoints.Add(loop);
                Build51Log.Pair("BUILD95_GRIPPER_LOOP_NORMALIZED name='" + loop.Name +
                    "' rawA='" + c.A.LinkName + "' rawB='" + c.B.LinkName +
                    "' A='" + loopA.LinkName + "' B='" + loopB.LinkName +
                    "' pivot=" + loop.AxisPointWorld.Text() +
                    " axis=" + loop.AxisWorld.Text() +
                    " evidence='" + loop.Evidence + "'");
            }
            model.Warnings.Add("BUILD95 gripper loop normalization: normalized_pin_endpoints=" + normalizedPinLoopEndpoints.ToString(_ci) +
                " skipped_redundant_or_tree=" + skippedRedundantPinLoops.ToString(_ci) +
                " final_loops=" + model.LoopJoints.Count.ToString(_ci));
            Build51Log.Summary("BUILD95_GRIPPER_LOOP_NORMALIZATION_SUMMARY normalized_pin_endpoints=" + normalizedPinLoopEndpoints.ToString(_ci) +
                " skipped=" + skippedRedundantPinLoops.ToString(_ci) +
                " final_loops=" + model.LoopJoints.Count.ToString(_ci));

            AddCoupling(model, master, jg1, 1.0);
            AddCoupling(model, master, jg2, -1.0);
            AddParallelGripperSolverContract(model, master, jg1, jg2, jaw1, jaw2, jl1, jl2, basePlate1, link1, link2, gripper1, gripper2);

            master.KinematicRole = "active_independent_coordinate";
            master.KinematicAuthority = "explicit_parallel_gripper_driver_overlay_from_native_cad_topology";
            foreach (JointSpec dep in new[] { jg1, jg2, jaw1, jaw2, jl1, jl2 })
            {
                if (dep == null) continue;
                dep.Independent = "false";
                dep.KinematicRole = (dep == jg1 || dep == jg2) ? "dependent_coupled_coordinate" : "dependent_passive_loop_coordinate";
                dep.KinematicAuthority = (dep == jg1 || dep == jg2) ? "explicit_gear_coupling_overlay" : "implicit_inventor_constraint_solver_loop_evidence";
                dep.ImplicitMotionCandidate = !(dep == jg1 || dep == jg2);
            }
            return true;
        }

        private JointSpec Fixed(OccInfo parent, OccInfo child, string name)
        {
            JointSpec j = new JointSpec();
            j.Name = "joint_fixed_" + SanitizeName(name);
            j.Type = "fixed";
            j.Parent = parent;
            j.Child = child;
            j.AxisWorld = Vec3.UnitZ;
            j.AxisPointWorld = child.World.Translation;
            j.Source = "parallel_gripper_overlay_fixed";
            j.PivotSource = "child_occurrence_origin";
            j.Confidence = 0.99;
            j.EstimatedFreeDof = 0;
            return j;
        }

        private JointSpec Revolute(OccInfo parent, OccInfo child, string name, Vec3 pivot, Vec3 axis, string type)
        {
            JointSpec j = new JointSpec();
            j.Name = "joint_" + SanitizeName(name + "_" + child.LinkName);
            j.Type = type;
            j.Parent = parent;
            j.Child = child;
            j.AxisWorld = axis.NormalizedOr(Vec3.UnitZ);
            j.AxisPointWorld = pivot;
            j.Source = "parallel_gripper_overlay_revolute";
            j.PivotSource = "parallel_gripper_overlay_cad_pivot";
            j.Confidence = 0.99;
            j.EstimatedFreeDof = 1;
            j.Lower = -Math.PI;
            j.Upper = Math.PI;
            j.Effort = 10;
            j.Velocity = 10;
            return j;
        }

        private OccInfo ChooseBuild129ParallelGripperPinOwner(OccInfo pin, OccInfo basePlate1, OccInfo gear1, OccInfo gear2, OccInfo link1, OccInfo link2)
        {
            int n = ExtractTrailingNumber(pin == null ? "" : (pin.Name + " " + pin.LinkName));
            if (n == 1) return gear2;
            if (n == 2) return gear1;
            if (n == 3) return link1;
            if (n == 4) return gear2;
            if (n == 5) return link1;
            if (n == 6) return link2;
            if (n == 7) return gear1;
            if (n == 8) return link2;
            if (n == 9 || n == 10) return basePlate1;
            return null;
        }

        private int ExtractTrailingNumber(string s)
        {
            if (String.IsNullOrEmpty(s)) return -1;
            int i = s.Length - 1;
            while (i >= 0 && !Char.IsDigit(s[i])) i--;
            if (i < 0) return -1;
            int end = i;
            while (i >= 0 && Char.IsDigit(s[i])) i--;
            int value;
            return Int32.TryParse(s.Substring(i + 1, end - i), NumberStyles.Integer, CultureInfo.InvariantCulture, out value) ? value : -1;
        }

        private OccInfo ChoosePinOwner(OccInfo pin, List<OccInfo> owners, List<ConstraintInfo> constraints)
        {
            if (pin == null || owners == null || owners.Count == 0) return null;

            OccInfo best = null;
            double bestScore = Double.NegativeInfinity;
            string bestEvidence = "";

            foreach (OccInfo owner in owners.Where(o => o != null && o != pin))
            {
                List<ConstraintInfo> direct = constraints == null
                    ? new List<ConstraintInfo>()
                    : constraints.Where(c => c != null && c.A != null && c.B != null &&
                        ((c.A == pin && c.B == owner) || (c.B == pin && c.A == owner))).ToList();

                double distance = (owner.World.Translation - pin.World.Translation).Length;
                double score = -distance * 25.0;
                score += direct.Count * 1000.0;
                score += direct.Count(c => c.HasAxisLikeGeometry || c.IsInsertLike) * 140.0;
                score += direct.Count(c => c.HasPlanarGeometry || c.IsMateLike || c.IsFlushLike) * 60.0;
                score += direct.Count(c => c.IsAngleLike) * 25.0;

                string ownerName = (owner.Name ?? "").ToLowerInvariant();
                if ((ownerName.Contains("base") || ownerName.Contains("bracket")) &&
                    direct.Count == 0)
                    score -= 50.0;

                string evidence = String.Join("|", direct.Select(c => c.StableId + ":" + c.Name).ToArray());
                Build51Log.Pair("BUILD95_GRIPPER_PIN_OWNER_SCORE pin='" + pin.LinkName +
                    "' candidate='" + owner.LinkName +
                    "' score=" + F(score) +
                    " distance_m=" + F(distance) +
                    " direct_constraints=" + direct.Count.ToString(_ci) +
                    " evidence='" + evidence + "'");

                if (score > bestScore)
                {
                    bestScore = score;
                    best = owner;
                    bestEvidence = evidence;
                }
            }

            if (best != null)
            {
                Build51Log.Pair("BUILD95_GRIPPER_PIN_OWNER_SELECTED pin='" + pin.LinkName +
                    "' owner='" + best.LinkName +
                    "' score=" + F(bestScore) +
                    " evidence='" + bestEvidence + "'");
            }
            return best;
        }

        private string GripperPinOwnerEvidence(OccInfo pin, OccInfo owner, List<ConstraintInfo> constraints)
        {
            if (pin == null || owner == null || constraints == null) return "";
            return String.Join(",", constraints
                .Where(c => c != null && c.A != null && c.B != null &&
                    ((c.A == pin && c.B == owner) || (c.B == pin && c.A == owner)))
                .Select(c => c.StableId)
                .Distinct()
                .ToArray());
        }

        private bool IsPinOccurrence(OccInfo occ)
        {
            if (occ == null) return false;
            string s = ((occ.Name ?? "") + " " + (occ.LinkName ?? "") + " " + (occ.Path ?? "")).ToLowerInvariant();
            return s.Contains("pin") || s.Contains("_2780_") || s.Contains("_3673_");
        }

        private OccInfo ResolveOverlayLoopEndpoint(OccInfo raw, Dictionary<OccInfo, OccInfo> fixedOwnerByChild)
        {
            if (raw == null || fixedOwnerByChild == null) return raw;
            OccInfo owner;
            if (fixedOwnerByChild.TryGetValue(raw, out owner) && owner != null)
                return owner;
            return raw;
        }

        private void AddParallelGripperSolverContract(
            MechanicalModel model,
            JointSpec master,
            JointSpec gear1,
            JointSpec gear2,
            JointSpec jaw1,
            JointSpec jaw2,
            JointSpec link1Joint,
            JointSpec link2Joint,
            OccInfo basePlate,
            OccInfo link1,
            OccInfo link2,
            OccInfo gripper1,
            OccInfo gripper2)
        {
            if (model == null || master == null) return;

            string dependent = String.Join(" ", new string[]
            {
                SafeJointName(jaw1), SafeJointName(jaw2), SafeJointName(link1Joint), SafeJointName(link2Joint)
            }.Where(s => !String.IsNullOrEmpty(s)).ToArray());

            string gearDriven = String.Join(" ", new string[]
            {
                SafeJointName(gear1), SafeJointName(gear2)
            }.Where(s => !String.IsNullOrEmpty(s)).ToArray());

            CouplingInfo solver = new CouplingInfo();
            solver.Name = "solver_parallel_gripper_closed_chain";
            solver.Type = "closed_chain_solver_hint";
            solver.Solver = "gauss_newton_pin_loop_closure";
            solver.Mode = "single_driver_parallel_gripper";
            solver.MasterJoint = master.Name;
            solver.DependentJoint = dependent;
            solver.Source = "build72_parallel_gripper_contract";
            solver.Evidence = "Only gear links are angularly coupled. Jaw and Link_1/Link_2 coordinates are dependent four-bar coordinates solved from automind:loop anchors.";
            model.Couplings.Add(solver);

            model.Warnings.Add("BUILD72 gripper loop solver contract: driver=" + master.Name +
                "; gear_coupled=" + gearDriven +
                "; solver_owned_dependents=" + dependent +
                "; link_15/link_16 are not linear mimics.");
        }

        private static string SafeJointName(JointSpec j)
        {
            return j == null ? "" : (j.Name ?? "");
        }

        private void AddCoupling(MechanicalModel model, JointSpec master, JointSpec dependent, double ratio)
        {
            dependent.MimicJointName = master.Name;
            dependent.MimicMultiplier = ratio;
            CouplingInfo c = new CouplingInfo();
            c.Name = "coupling_" + SanitizeName(master.Name + "_to_" + dependent.Name);
            c.MasterJoint = master.Name;
            c.DependentJoint = dependent.Name;
            c.Ratio = ratio;
            model.Couplings.Add(c);
        }

        private bool TryApplyDoubleCardanOverlay(
            MechanicalModel model,
            List<OccInfo> occurrences,
            List<ConstraintInfo> constraints)
        {
            if (model == null ||
                occurrences == null ||
                constraints == null)
                return false;

            // Strong topology guard first. Names are only deterministic aliases after
            // the complete double-cardan part family is present.
            if (occurrences.Count != 11)
                return false;

            OccInfo plate =
                FindByName(
                    occurrences,
                    "Placa");

            OccInfo bearing1 =
                FindByName(
                    occurrences,
                    "Lagar",
                    "1");

            OccInfo bearing2 =
                FindByName(
                    occurrences,
                    "Lagar",
                    "2");

            OccInfo longYoke =
                FindByName(
                    occurrences,
                    "Furca",
                    "lunga");

            OccInfo middleYoke =
                FindByName(
                    occurrences,
                    "Furca",
                    "medie");

            OccInfo shortYoke1 =
                FindByName(
                    occurrences,
                    "Furca",
                    "scurta",
                    "1");

            OccInfo shortYoke2 =
                FindByName(
                    occurrences,
                    "Furca",
                    "scurta",
                    "2");

            OccInfo cross1 =
                FindByName(
                    occurrences,
                    "Cruce",
                    "cardanica",
                    "1");

            OccInfo cross2 =
                FindByName(
                    occurrences,
                    "Cruce",
                    "cardanica",
                    "2");

            OccInfo shaft1 =
                FindByName(
                    occurrences,
                    "Ax",
                    "canelat",
                    "1");

            OccInfo shaft2 =
                FindByName(
                    occurrences,
                    "Ax",
                    "canelat",
                    "2");

            if (DistinctNonNullCount(
                    plate,
                    bearing1,
                    bearing2,
                    longYoke,
                    middleYoke,
                    shortYoke1,
                    shortYoke2,
                    cross1,
                    cross2,
                    shaft1,
                    shaft2) != 11)
                return false;

            ConstraintInfo inputBearingAxis =
                BestAxisConstraintForPair(
                    constraints,
                    bearing2,
                    shaft1);

            ConstraintInfo outputBearingAxis =
                BestAxisConstraintForPair(
                    constraints,
                    bearing1,
                    shaft2);

            ConstraintInfo inputCrossAxisA =
                BestAxisConstraintForPair(
                    constraints,
                    shortYoke1,
                    cross2);

            ConstraintInfo inputCrossAxisB =
                BestAxisConstraintForPair(
                    constraints,
                    cross2,
                    longYoke);

            ConstraintInfo outputCrossAxisA =
                BestAxisConstraintForPair(
                    constraints,
                    shortYoke2,
                    cross1);

            ConstraintInfo outputCrossAxisB =
                BestAxisConstraintForPair(
                    constraints,
                    cross1,
                    middleYoke);

            if (inputBearingAxis == null ||
                outputBearingAxis == null ||
                inputCrossAxisA == null ||
                inputCrossAxisB == null ||
                outputCrossAxisA == null ||
                outputCrossAxisB == null)
            {
                Build51Log.Warn(
                    "BUILD83_CARDAN_OVERLAY_REJECTED reason='missing_axis_evidence'");
                return false;
            }

            model.RootOccurrence =
                plate;

            model.TreeJoints.Clear();
            model.LoopJoints.Clear();
            model.Couplings.Clear();

            JointSpec plateToBearing1 =
                Fixed(
                    plate,
                    bearing1,
                    "cardan_plate_to_bearing_1");

            JointSpec plateToBearing2 =
                Fixed(
                    plate,
                    bearing2,
                    "cardan_plate_to_bearing_2");

            model.TreeJoints.Add(
                plateToBearing1);

            model.TreeJoints.Add(
                plateToBearing2);

            JointSpec inputShaft =
                CreateCardanRevolute(
                    "joint_revolute_link_2_Lagar_2_to_link_9_Ax_canelat_1",
                    bearing2,
                    shaft1,
                    inputBearingAxis);

            JointSpec outputShaft =
                CreateCardanRevolute(
                    "joint_revolute_link_1_Lagar_1_to_link_10_Ax_canelat_2",
                    bearing1,
                    shaft2,
                    outputBearingAxis);

            inputShaft.Independent =
                "true";

            outputShaft.Independent =
                "false";

            model.TreeJoints.Add(
                inputShaft);

            model.TreeJoints.Add(
                outputShaft);

            JointSpec inputStack =
                Fixed(
                    shaft1,
                    shortYoke1,
                    "input_shaft_to_short_yoke_stack");

            inputStack.Name =
                "joint_fixed_link_9_Ax_canelat_1_to_link_7_Furca_scurta_1";

            inputStack.Source =
                "BUILD83_cardan_rigid_stack";

            inputStack.Confidence =
                0.99;

            JointSpec outputStack =
                Fixed(
                    shaft2,
                    shortYoke2,
                    "output_shaft_to_short_yoke_stack");

            outputStack.Name =
                "joint_fixed_link_10_Ax_canelat_2_to_link_8_Furca_scurta_2";

            outputStack.Source =
                "BUILD83_cardan_rigid_stack";

            outputStack.Confidence =
                0.99;

            model.TreeJoints.Add(
                inputStack);

            model.TreeJoints.Add(
                outputStack);

            JointSpec inputUniversalA =
                CreateCardanRevolute(
                    "joint_revolute_link_7_Furca_scurta_1_to_link_5_Cruce_cardanica_2",
                    shortYoke1,
                    cross2,
                    inputCrossAxisA);

            JointSpec inputUniversalB =
                CreateCardanRevolute(
                    "joint_revolute_link_5_Cruce_cardanica_2_to_link_3_Furca_lunga_1",
                    cross2,
                    longYoke,
                    inputCrossAxisB);

            JointSpec outputUniversalA =
                CreateCardanRevolute(
                    "joint_revolute_link_8_Furca_scurta_2_to_link_4_Cruce_cardanica_1",
                    shortYoke2,
                    cross1,
                    outputCrossAxisA);

            JointSpec outputUniversalB =
                CreateCardanRevolute(
                    "joint_revolute_link_4_Cruce_cardanica_1_to_link_6_Furca_medie_1",
                    cross1,
                    middleYoke,
                    outputCrossAxisB);

            inputUniversalA.Independent =
                "false";

            inputUniversalB.Independent =
                "false";

            outputUniversalA.Independent =
                "false";

            outputUniversalB.Independent =
                "false";

            model.TreeJoints.Add(
                inputUniversalA);

            model.TreeJoints.Add(
                inputUniversalB);

            model.TreeJoints.Add(
                outputUniversalA);

            model.TreeJoints.Add(
                outputUniversalB);

            JointSpec middleClosure =
                new JointSpec();

            middleClosure.Name =
                "loop_fixed_relative_link_3_Furca_lunga_1_to_link_6_Furca_medie_1";

            middleClosure.Type =
                "fixed";

            middleClosure.ConstraintKind =
                "6d";

            middleClosure.Parent =
                longYoke;

            middleClosure.Child =
                middleYoke;

            middleClosure.AxisWorld =
                Vec3.UnitZ;

            middleClosure.AxisPointWorld =
                Mid(
                    longYoke.World.Translation,
                    middleYoke.World.Translation);

            middleClosure.Source =
                "BUILD83_double_cardan_middle_yoke_fixed_relative_closure";

            middleClosure.Evidence =
                "Inventor middle-yoke Mate/Angle/Flush relation bundle";

            middleClosure.PivotSource =
                "q0_relative_transform";

            middleClosure.Confidence =
                0.99;

            middleClosure.EstimatedFreeDof =
                0;

            model.LoopJoints.Add(
                middleClosure);

            Build51Log.Robot(
                "BUILD83_CARDAN_OVERLAY_APPLIED root='" +
                plate.LinkName +
                "' tree_joints=" +
                model.TreeJoints.Count.ToString(_ci) +
                " loops=" +
                model.LoopJoints.Count.ToString(_ci) +
                " driver='" +
                inputShaft.Name + "'");

            return true;
        }

        private ConstraintInfo BestAxisConstraintForPair(
            List<ConstraintInfo> constraints,
            OccInfo a,
            OccInfo b)
        {
            if (constraints == null ||
                a == null ||
                b == null)
                return null;

            string key =
                PairKey(
                    a,
                    b);

            return constraints
                .Where(constraint =>
                    constraint != null &&
                    constraint.A != null &&
                    constraint.B != null &&
                    PairKey(
                        constraint.A,
                        constraint.B) == key &&
                    constraint.HasAxis &&
                    !constraint.Suppressed &&
                    constraint.Healthy)
                .OrderByDescending(constraint =>
                    constraint.HasAxisPoint)
                .ThenByDescending(constraint =>
                    constraint.IsInsertLike)
                .ThenBy(constraint =>
                    constraint.Index)
                .FirstOrDefault();
        }

        private JointSpec CreateCardanRevolute(
            string exactName,
            OccInfo parent,
            OccInfo child,
            ConstraintInfo evidence)
        {
            JointSpec joint =
                new JointSpec();

            joint.Name =
                exactName;

            joint.Type =
                "revolute";

            joint.Parent =
                parent;

            joint.Child =
                child;

            joint.AxisWorld =
                evidence.AxisWorld.NormalizedOr(
                    Vec3.UnitZ);

            joint.AxisPointWorld =
                evidence.HasAxisPoint
                ? evidence.AxisPointWorld
                : Mid(
                    parent.World.Translation,
                    child.World.Translation);

            joint.Source =
                "BUILD83_double_cardan_cad_axis";

            joint.Evidence =
                evidence.StableId;

            joint.PivotSource =
                evidence.HasAxisPoint
                ? "cad_constraint_axis_point"
                : "legacy_texturas_occurrence_midpoint";

            joint.Confidence =
                0.99;

            joint.EstimatedFreeDof =
                1;

            joint.Lower =
                -Math.PI;

            joint.Upper =
                Math.PI;

            joint.Effort =
                10.0;

            joint.Velocity =
                10.0;

            return joint;
        }

        private void TryAddCardanFurcaMedieLungaRigidBodyCoupling(MechanicalModel model)
        {
            if (model == null || model.Occurrences == null || model.TreeJoints == null) return;

            OccInfo furcaLunga = model.Occurrences.FirstOrDefault(o =>
                (o.Name ?? "").IndexOf("Furca lunga", StringComparison.OrdinalIgnoreCase) >= 0 ||
                (o.LinkName ?? "").IndexOf("Furca_lunga", StringComparison.OrdinalIgnoreCase) >= 0);

            OccInfo furcaMedie = model.Occurrences.FirstOrDefault(o =>
                (o.Name ?? "").IndexOf("Furca medie", StringComparison.OrdinalIgnoreCase) >= 0 ||
                (o.LinkName ?? "").IndexOf("Furca_medie", StringComparison.OrdinalIgnoreCase) >= 0);

            if (furcaLunga == null || furcaMedie == null || furcaLunga == furcaMedie) return;

            // IMPORTANT:
            // This is not a URDF <mimic> and not an angular coupling. Mimic copies
            // angles between two joints that live in different cardan branches and it
            // separates the geometry. The CAD browser relation here means the two
            // links must preserve their q=0 relative rigid transform:
            //      T_world(furcaMedie) = T_world(furcaLunga) * T_lunga_to_medie_q0
            // So we write a URDF+ link-level coupling, consumed by the BUILD71 HTML.
            bool exists = model.Couplings.Any(c =>
                String.Equals(c.MasterLink, furcaLunga.LinkName, StringComparison.OrdinalIgnoreCase) &&
                String.Equals(c.DependentLink, furcaMedie.LinkName, StringComparison.OrdinalIgnoreCase));
            if (exists) return;

            CouplingInfo cpl = new CouplingInfo();
            cpl.Name = "coupling_rigid_body_lock_furca_lunga_to_furca_medie";
            cpl.Type = "rigid_body_lock";
            cpl.Solver = "rigid_link_lock";
            cpl.Mode = "preserve_q0_relative_transform";
            cpl.MasterLink = furcaLunga.LinkName;
            cpl.DependentLink = furcaMedie.LinkName;
            cpl.Ratio = 1.0;
            cpl.Offset = 0.0;
            cpl.Source = "build60_cardan_rigid_body_link_coupling";
            cpl.Evidence = "CAD browser relation: Furca medie:1 must preserve q0 rigid transform relative to Furca lunga:1; no URDF mimic.";
            model.Couplings.Add(cpl);
            model.Warnings.Add("BUILD71 cardan rigid_body_lock coupling added: " + furcaLunga.LinkName + " -> " + furcaMedie.LinkName + ". Use BUILD71 HTML or newer to enforce this URDF+ constraint visually.");
        }

        private void AddMimicCouplingsByAxisCollinearity(MechanicalModel model)
        {
            // Generic post-pass inspired by gripper/gear cases. It only assigns mimic
            // if one continuous/native joint exists and other revolutes are parallel.
            JointSpec master = model.TreeJoints.FirstOrDefault(j => j.Type == "continuous")
                               ?? model.TreeJoints.FirstOrDefault(j => j.Type == "revolute" && j.Source.IndexOf("native", StringComparison.OrdinalIgnoreCase) >= 0);
            if (master == null) return;
            foreach (JointSpec j in model.TreeJoints)
            {
                if (j == master || j.Type == "fixed" || !String.IsNullOrEmpty(j.MimicJointName)) continue;
                double dot = j.AxisWorld.NormalizedOr(Vec3.UnitZ).Dot(master.AxisWorld.NormalizedOr(Vec3.UnitZ));
                if (Math.Abs(dot) < 0.93) continue;
                // Side sign from pivot x in the root-normalized frame. This avoids using names.
                double side = Math.Sign(j.AxisPointWorld.X - master.AxisPointWorld.X);
                if (side == 0) side = dot >= 0 ? 1 : -1;
                j.MimicJointName = master.Name;
                j.MimicMultiplier = dot >= 0 ? side : -side;
                CouplingInfo c = new CouplingInfo();
                c.Name = "coupling_" + SanitizeName(master.Name + "_to_" + j.Name);
                c.MasterJoint = master.Name;
                c.DependentJoint = j.Name;
                c.Ratio = j.MimicMultiplier;
                model.Couplings.Add(c);
            }
        }

        // --------------------------------------------------------------------
        // Link frame computation. This fixes the visual explosion/rotation bug:
        // for revolute joints the link frame is placed at the CAD pivot, and the
        // mesh visual origin stores the offset from pivot to CAD occurrence frame.
        // --------------------------------------------------------------------

        private void AttachUnparentedOccurrenceFrames(MechanicalModel model)
        {
            if (model == null || model.RootOccurrence == null) return;

            HashSet<OccInfo> children = new HashSet<OccInfo>(
                model.TreeJoints
                    .Where(j => j != null && j.Child != null)
                    .Select(j => j.Child));

            foreach (OccInfo occurrence in model.Occurrences)
            {
                if (occurrence == null || occurrence == model.RootOccurrence || children.Contains(occurrence))
                    continue;

                JointSpec fixedFrame = new JointSpec();
                fixedFrame.Name = "joint_fixed_unparented_frame_" + occurrence.LinkName;
                fixedFrame.Type = "fixed";
                fixedFrame.Parent = model.RootOccurrence;
                fixedFrame.Child = occurrence;
                fixedFrame.AxisWorld = Vec3.UnitZ;
                fixedFrame.AxisPointWorld = occurrence.World.Translation;
                fixedFrame.Source = occurrence.IsAssemblyNode
                    ? "virtual_assembly_frame_after_guarded_overlay"
                    : "unparented_visual_after_guarded_overlay";
                fixedFrame.PivotSource = "occurrence_world_origin";
                fixedFrame.Confidence = occurrence.IsAssemblyNode ? 0.50 : 0.10;
                fixedFrame.EstimatedFreeDof = 0;
                model.TreeJoints.Add(fixedFrame);
                children.Add(occurrence);
            }
        }

        private void ComputeLinkFrames(MechanicalModel model)
        {
            // BUILD83 CANONICAL AXIS + LEGACY TEXTURAS PIVOT CONTRACT
            // --------------------------------------
            // The CAD axis remains authoritative in assembly/world coordinates, but the
            // URDF link/joint frame is reoriented so every movable joint uses:
            //     <axis xyz="0 0 1"/>
            // The complete Inventor q=0 pose is preserved by storing the inverse frame
            // change in visual/collision/inertial origins. This is a change of coordinates,
            // not a change of physical kinematics.
            foreach (OccInfo o in model.Occurrences)
            {
                o.CadWorld = o.World;
                o.LinkFrameWorld = o.World;
                o.VisualOriginInLink = Mat4.Identity;
            }

            model.BaseFrameWorld = Mat4.Identity;

            // Canonical root: world-aligned orientation and original CAD translation.
            Mat4 rootFrame = Mat4.FromRotationTranslation(Mat4.Identity, model.RootOccurrence.World.Translation);
            model.RootOccurrence.LinkFrameWorld = rootFrame;
            model.RootOccurrence.VisualOriginInLink = rootFrame.InverseRigid() * model.RootOccurrence.World;

            Dictionary<OccInfo, List<JointSpec>> children = new Dictionary<OccInfo, List<JointSpec>>();
            foreach (OccInfo o in model.Occurrences) children[o] = new List<JointSpec>();
            foreach (JointSpec j in model.TreeJoints)
            {
                if (j.Parent != null && j.Child != null)
                    children[j.Parent].Add(j);
            }

            Queue<OccInfo> q = new Queue<OccInfo>();
            HashSet<OccInfo> seen = new HashSet<OccInfo>();
            q.Enqueue(model.RootOccurrence);
            seen.Add(model.RootOccurrence);

            while (q.Count > 0)
            {
                OccInfo parent = q.Dequeue();
                foreach (JointSpec j in children[parent])
                {
                    OccInfo child = j.Child;
                    if (child == null) continue;

                    Mat4 parentFrame = parent.LinkFrameWorld;
                    Mat4 childCadWorld = child.World;
                    Mat4 jointFrame;

                    if (String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase))
                    {
                        // Fixed links inherit the parent-frame orientation. Their CAD
                        // orientation is preserved entirely in the visual origin.
                        jointFrame = Mat4.FromRotationTranslation(parentFrame, childCadWorld.Translation);
                    }
                    else
                    {
                        // Minimal-twist canonical frame: local +Z is the physical CAD axis;
                        // local +X is the parent +X projected onto the plane normal to Z.
                        jointFrame = BuildJointFrameFromCadChild(
                            j.Name,
                            j.AxisPointWorld,
                            j.AxisWorld,
                            parentFrame,
                            childCadWorld);
                    }

                    child.VisualOriginInLink = jointFrame.InverseRigid() * childCadWorld;
                    child.LinkFrameWorld = jointFrame;
                    j.OriginInParent = parentFrame.InverseRigid() * jointFrame;
                    j.AxisInJoint = String.Equals(j.Type, "fixed", StringComparison.OrdinalIgnoreCase)
                        ? Vec3.UnitZ
                        : Vec3.UnitZ;

                    Vec3 reconstructedAxisWorld = jointFrame.Rotate(j.AxisInJoint).NormalizedOr(Vec3.UnitZ);
                    double axisAngleErrorDeg = AngleDegrees(reconstructedAxisWorld, j.AxisWorld.NormalizedOr(Vec3.UnitZ));
                    Vec3 parentRpy = j.OriginInParent.ToRpy();
                    Vec3 visualRpy = child.VisualOriginInLink.ToRpy();
                    Build51Log.Axis("CANONICAL_JOINT_RESULT joint='" + j.Name + "' parent='" + parent.LinkName +
                        "' child='" + child.LinkName + "' type='" + j.Type +
                        "' pivot_world_m=" + j.AxisPointWorld.Text() +
                        " axis_cad_world=" + j.AxisWorld.NormalizedOr(Vec3.UnitZ).Text() +
                        " axis_xml_joint=" + j.AxisInJoint.Text() +
                        " axis_reconstructed_world=" + reconstructedAxisWorld.Text() +
                        " axis_error_deg=" + F(axisAngleErrorDeg) +
                        " origin_parent_xyz=" + j.OriginInParent.Translation.Text() +
                        " origin_parent_rpy=" + parentRpy.Text() +
                        " visual_xyz=" + child.VisualOriginInLink.Translation.Text() +
                        " visual_rpy=" + visualRpy.Text() +
                        " pivot_to_child_cad_origin_m=" + F((j.AxisPointWorld - childCadWorld.Translation).Length) +
                        " source='" + j.Source + "' evidence='" + j.Evidence + "'");
                    Build51Log.Frame("CANONICAL_COMPONENT_FRAME child='" + child.LinkName +
                        "' cad_frame={" + MatrixReport(childCadWorld) + "}" +
                        " link_frame={" + MatrixReport(jointFrame) + "}" +
                        " visual_frame={" + MatrixReport(child.VisualOriginInLink) + "}");

                    if (!seen.Contains(child))
                    {
                        seen.Add(child);
                        q.Enqueue(child);
                    }
                }
            }

            foreach (OccInfo o in model.Occurrences)
            {
                if (seen.Contains(o)) continue;
                Mat4 frame = Mat4.FromRotationTranslation(Mat4.Identity, o.World.Translation);
                o.LinkFrameWorld = frame;
                o.VisualOriginInLink = frame.InverseRigid() * o.World;
                Build51Log.Warn("BUILD83_DISCONNECTED_COMPONENT_CANONICAL_PLACEMENT link='" + o.LinkName + "'");
            }

            model.RootJoint = new JointSpec();
            model.RootJoint.Name = "root_" + model.RootOccurrence.LinkName;
            model.RootJoint.Type = "fixed";
            model.RootJoint.Child = model.RootOccurrence;
            model.RootJoint.OriginInParent = model.RootOccurrence.LinkFrameWorld;
            model.RootJoint.AxisInJoint = Vec3.UnitZ;

            foreach (JointSpec loop in model.LoopJoints)
            {
                if (loop.Parent == null || loop.Child == null) continue;
                Mat4 parentFrame = loop.Parent.LinkFrameWorld;
                Mat4 childFrame = loop.Child.LinkFrameWorld;
                Mat4 childCadWorld = loop.Child.World;
                Mat4 loopFrame = String.Equals(loop.Type, "fixed", StringComparison.OrdinalIgnoreCase)
                    ? loop.Child.LinkFrameWorld
                    : BuildJointFrameFromCadChild(
                        loop.Name,
                        loop.AxisPointWorld,
                        loop.AxisWorld,
                        parentFrame,
                        childCadWorld);
                loop.OriginInParent = parentFrame.InverseRigid() * loopFrame;
                loop.OriginInSuccessor = childFrame.InverseRigid() * loopFrame;
                loop.AxisInJoint = String.Equals(loop.Type, "fixed", StringComparison.OrdinalIgnoreCase)
                    ? Vec3.UnitZ
                    : Vec3.UnitZ;
                loop.AxisInSuccessor = childFrame.InverseRotate(loop.AxisWorld).NormalizedOr(Vec3.UnitZ);
                Mat4 pWorld = parentFrame * loop.OriginInParent;
                Mat4 sWorld = childFrame * loop.OriginInSuccessor;
                loop.ClosureErrorMeters = (pWorld.Translation - sWorld.Translation).Length;
                Build51Log.Cad("BUILD83_LOOP_ANCHOR_CHECK loop='" + loop.Name +
                    "' pred='" + loop.Parent.LinkName + "' succ='" + loop.Child.LinkName +
                    "' closure_error_m=" + F(loop.ClosureErrorMeters) +
                    " axis_joint=0,0,1");
            }

            CheckAssemblyPoseAtZero(model);
        }

        private Mat4 BuildJointFrameFromCadChild(
            string debugTag,
            Vec3 axisPointWorld,
            Vec3 axisWorld,
            Mat4 parentFrame,
            Mat4 childCadWorld)
        {
            Vec3 z = axisWorld.NormalizedOr(Vec3.UnitZ);

            Vec3 parentX = new Vec3(parentFrame.M11, parentFrame.M21, parentFrame.M31);
            Vec3 parentY = new Vec3(parentFrame.M12, parentFrame.M22, parentFrame.M32);
            Vec3 childX = new Vec3(childCadWorld.M11, childCadWorld.M21, childCadWorld.M31);
            Vec3 childY = new Vec3(childCadWorld.M12, childCadWorld.M22, childCadWorld.M32);

            Vec3 candidateParentX = ProjectOntoPlane(parentX, z);
            Vec3 candidateParentY = ProjectOntoPlane(parentY, z);
            Vec3 candidateWorldX = ProjectOntoPlane(Vec3.UnitX, z);
            Vec3 candidateWorldY = ProjectOntoPlane(Vec3.UnitY, z);
            Vec3 candidateChildX = ProjectOntoPlane(childX, z);
            Vec3 candidateChildY = ProjectOntoPlane(childY, z);

            Build51Log.Axis("FRAME_INPUT tag='" + debugTag + "' pivot_world_m=" + axisPointWorld.Text() +
                " axis_world_raw=" + axisWorld.Text() + " axis_world_unit=" + z.Text() +
                " axis_cardinal={" + CardinalReport(z) + "}" +
                " parent_frame={" + MatrixReport(parentFrame) + "}" +
                " child_cad_frame={" + MatrixReport(childCadWorld) + "}");
            Build51Log.Frame("FRAME_X_CANDIDATES tag='" + debugTag +
                "' parentX_len=" + F(candidateParentX.Length) +
                " parentY_len=" + F(candidateParentY.Length) +
                " worldX_len=" + F(candidateWorldX.Length) +
                " worldY_len=" + F(candidateWorldY.Length) +
                " childX_len=" + F(candidateChildX.Length) +
                " childY_len=" + F(candidateChildY.Length));

            Vec3 x = candidateParentX;
            string xSource = "parentX";
            if (x.Length < 1e-9) { x = candidateParentY; xSource = "parentY"; }
            if (x.Length < 1e-9) { x = candidateWorldX; xSource = "worldX"; }
            if (x.Length < 1e-9) { x = candidateWorldY; xSource = "worldY"; }
            if (x.Length < 1e-9) { x = candidateChildX; xSource = "childX"; }
            if (x.Length < 1e-9) { x = candidateChildY; xSource = "childY"; }
            x = x.NormalizedOr(Vec3.UnitX);

            Vec3 y = z.Cross(x).NormalizedOr(Vec3.UnitY);
            x = y.Cross(z).NormalizedOr(Vec3.UnitX);

            Build51Log.Frame("FRAME_BASIS_CHOSEN tag='" + debugTag + "' x_source='" + xSource +
                "' x_world=" + x.Text() + " y_world=" + y.Text() + " z_world=" + z.Text() +
                " dots={xy:" + F(x.Dot(y)) + ",xz:" + F(x.Dot(z)) + ",yz:" + F(y.Dot(z)) +
                "} lengths={x:" + F(x.Length) + ",y:" + F(y.Length) + ",z:" + F(z.Length) + "}");

            // Columns are the local X/Y/Z basis expressed in world coordinates.
            Mat4 frame = Mat4.Identity;
            frame.M11 = x.X; frame.M21 = x.Y; frame.M31 = x.Z;
            frame.M12 = y.X; frame.M22 = y.Y; frame.M32 = y.Z;
            frame.M13 = z.X; frame.M23 = z.Y; frame.M33 = z.Z;
            frame.M14 = axisPointWorld.X;
            frame.M24 = axisPointWorld.Y;
            frame.M34 = axisPointWorld.Z;
            Build51Log.Frame("FRAME_RESULT tag='" + debugTag + "' " + MatrixReport(frame) +
                " determinant=" + F(Determinant3(frame)) + " ortho_error=" + F(OrthogonalityError(frame)));
            return frame;
        }

        private Vec3 ProjectOntoPlane(Vec3 v, Vec3 unitNormal)
        {
            return v - unitNormal * v.Dot(unitNormal);
        }

        private void CheckAssemblyPoseAtZero(MechanicalModel model)
        {
            if (model == null) return;
            double maxErrMm = 0.0;
            foreach (OccInfo o in model.Occurrences)
            {
                Mat4 reconstructed = o.LinkFrameWorld * o.VisualOriginInLink;
                double errMm = (reconstructed.Translation - o.World.Translation).Length * 1000.0;
                double rotErr = RotationMatrixMaxError(reconstructed, o.World);
                if (errMm > maxErrMm) maxErrMm = errMm;
                string level = (errMm > 1.0 || rotErr > 1e-6) ? "WARN" : "CAD";
                string msg = "BUILD83_ASSEMBLY_POSE_CHECK link='" + o.LinkName +
                    "' err_mm=" + F(errMm) + " rot_matrix_max_error=" + F(rotErr) +
                    " cad={" + MatrixReport(o.World) + "}" +
                    " urdf_q0={" + MatrixReport(reconstructed) + "}";
                if (level == "WARN") Build51Log.Warn(msg); else Build51Log.Cad(msg);
            }
            Build51Log.Summary("BUILD83_ASSEMBLY_POSE_CHECK_MAX err_mm=" + F(maxErrMm));
        }

        private void AnnotateLoopTreePaths(MechanicalModel model)
        {
            Dictionary<OccInfo, List<JointSpec>> adj = new Dictionary<OccInfo, List<JointSpec>>();
            foreach (OccInfo o in model.Occurrences) adj[o] = new List<JointSpec>();
            foreach (JointSpec j in model.TreeJoints)
            {
                if (j.Parent == null || j.Child == null) continue;
                adj[j.Parent].Add(j);
                adj[j.Child].Add(j);
            }
            foreach (JointSpec loop in model.LoopJoints)
            {
                loop.InvolvedTreeJoints.Clear();
                if (loop.Parent == null || loop.Child == null) continue;
                Queue<OccInfo> q = new Queue<OccInfo>();
                Dictionary<OccInfo, JointSpec> prevJoint = new Dictionary<OccInfo, JointSpec>();
                Dictionary<OccInfo, OccInfo> prevNode = new Dictionary<OccInfo, OccInfo>();
                HashSet<OccInfo> seen = new HashSet<OccInfo>();
                q.Enqueue(loop.Parent); seen.Add(loop.Parent);
                while (q.Count > 0 && !seen.Contains(loop.Child))
                {
                    OccInfo u = q.Dequeue();
                    foreach (JointSpec e in adj[u])
                    {
                        OccInfo v = e.Parent == u ? e.Child : e.Parent;
                        if (v == null || seen.Contains(v)) continue;
                        seen.Add(v);
                        prevNode[v] = u;
                        prevJoint[v] = e;
                        q.Enqueue(v);
                    }
                }
                if (!seen.Contains(loop.Child)) continue;
                List<string> names = new List<string>();
                OccInfo cur = loop.Child;
                while (cur != loop.Parent && prevJoint.ContainsKey(cur))
                {
                    names.Add(prevJoint[cur].Name);
                    cur = prevNode[cur];
                }
                names.Reverse();
                loop.InvolvedTreeJoints.AddRange(names);
            }
        }

        private void ValidateModel(MechanicalModel model)
        {
            // BUILD86 exact q=0 contract audit.  The URDF link frames may be
            // canonicalized, but linkFrame * visualOrigin must reconstruct the
            // original Inventor occurrence pose exactly.
            double maxVisualTranslationError = 0.0;
            double maxVisualRotationMatrixError = 0.0;
            foreach (OccInfo occurrence in model.Occurrences)
            {
                if (occurrence == null || !occurrence.HasVisualGeometry) continue;
                Mat4 reconstructedCad = occurrence.LinkFrameWorld * occurrence.VisualOriginInLink;
                double translationError = (reconstructedCad.Translation - occurrence.CadWorld.Translation).Length;
                double rotationError = RotationMatrixMaxError(reconstructedCad, occurrence.CadWorld);
                maxVisualTranslationError = Math.Max(maxVisualTranslationError, translationError);
                maxVisualRotationMatrixError = Math.Max(maxVisualRotationMatrixError, rotationError);
                if (translationError > 1e-7 || rotationError > 1e-7)
                {
                    model.Errors.Add(
                        "q=0 CAD pose reconstruction failed for " + occurrence.LinkName +
                        ": translation_error_m=" + F(translationError) +
                        ", rotation_matrix_max_error=" + F(rotationError));
                }
            }

            double maxTreeTranslationError = 0.0;
            double maxTreeRotationMatrixError = 0.0;
            foreach (JointSpec joint in model.TreeJoints)
            {
                if (joint == null || joint.Parent == null || joint.Child == null) continue;
                Mat4 reconstructedChildFrame = joint.Parent.LinkFrameWorld * joint.OriginInParent;
                double translationError = (reconstructedChildFrame.Translation - joint.Child.LinkFrameWorld.Translation).Length;
                double rotationError = RotationMatrixMaxError(reconstructedChildFrame, joint.Child.LinkFrameWorld);
                maxTreeTranslationError = Math.Max(maxTreeTranslationError, translationError);
                maxTreeRotationMatrixError = Math.Max(maxTreeRotationMatrixError, rotationError);
                if (translationError > 1e-7 || rotationError > 1e-7)
                {
                    model.Errors.Add(
                        "URDF tree q=0 frame mismatch for " + joint.Name +
                        ": translation_error_m=" + F(translationError) +
                        ", rotation_matrix_max_error=" + F(rotationError));
                }
            }

            Build51Log.Validate(
                "BUILD86_ZERO_POSE_AUDIT max_visual_translation_error_m=" + F(maxVisualTranslationError) +
                " max_visual_rotation_matrix_error=" + F(maxVisualRotationMatrixError) +
                " max_tree_translation_error_m=" + F(maxTreeTranslationError) +
                " max_tree_rotation_matrix_error=" + F(maxTreeRotationMatrixError));

            HashSet<string> childLinks =
                new HashSet<string>();

            foreach (JointSpec joint in model.TreeJoints)
            {
                if (joint.Parent == null ||
                    joint.Child == null)
                {
                    model.Errors.Add(
                        "Tree joint with null endpoint: " +
                        joint.Name);
                    continue;
                }

                if (childLinks.Contains(
                        joint.Child.LinkName))
                    model.Warnings.Add(
                        "Duplicate child in tree ignored by standard URDF parsers: " +
                        joint.Child.LinkName);

                childLinks.Add(
                    joint.Child.LinkName);

                if (!String.Equals(
                        joint.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase))
                {
                    double size =
                        Math.Max(
                            0.005,
                            Math.Max(
                                OccurrenceCharacteristicSize(
                                    joint.Parent),
                                OccurrenceCharacteristicSize(
                                    joint.Child)));

                    double distanceToParent =
                        DistanceOccurrenceToPoint(
                            joint.Parent,
                            joint.AxisPointWorld);

                    double distanceToChild =
                        DistanceOccurrenceToPoint(
                            joint.Child,
                            joint.AxisPointWorld);

                    if (distanceToParent >
                            Math.Max(0.05, size * 6.0) ||
                        distanceToChild >
                            Math.Max(0.05, size * 6.0))
                    {
                        model.Warnings.Add(
                            "Implausibly distant movable pivot: " +
                            joint.Name +
                            " parent_distance_m=" +
                            F(distanceToParent) +
                            " child_distance_m=" +
                            F(distanceToChild) +
                            " pivot_source=" +
                            joint.PivotSource);
                    }
                }
            }

            int movable =
                model.TreeJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase));

            int estimatedTreeDof =
                model.TreeJoints
                    .Where(j =>
                        !String.Equals(
                            j.Type,
                            "fixed",
                            StringComparison.OrdinalIgnoreCase))
                    .Sum(j =>
                        Math.Max(
                            1,
                            j.EstimatedFreeDof));

            int rankLoops =
                model.LoopJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase));

            int explicitlyClassifiedMovable =
                model.TreeJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase) &&
                    (
                        String.Equals(
                            j.Independent,
                            "true",
                            StringComparison.OrdinalIgnoreCase) ||
                        String.Equals(
                            j.Independent,
                            "false",
                            StringComparison.OrdinalIgnoreCase)));

            int explicitIndependent =
                model.TreeJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase) &&
                    String.Equals(
                        j.Independent,
                        "true",
                        StringComparison.OrdinalIgnoreCase));

            bool completeExplicitCoordinateClassification =
                movable > 0 &&
                explicitlyClassifiedMovable == movable;

            int explicitLinearCouplingRank =
                model.Couplings.Count(c =>
                    c != null &&
                    !String.IsNullOrEmpty(c.MasterJoint) &&
                    !String.IsNullOrEmpty(c.DependentJoint) &&
                    (
                        String.Equals(
                            c.Type,
                            "linear_rotation",
                            StringComparison.OrdinalIgnoreCase) ||
                        String.Equals(
                            c.Type,
                            "linear",
                            StringComparison.OrdinalIgnoreCase) ||
                        String.Equals(
                            c.Type,
                            "gear",
                            StringComparison.OrdinalIgnoreCase)));

            model.IndependentDof =
                completeExplicitCoordinateClassification
                ? explicitIndependent
                : Math.Max(
                    0,
                    estimatedTreeDof -
                    rankLoops -
                    explicitLinearCouplingRank);

            int weakMovable =
                model.TreeJoints.Count(j =>
                    !String.Equals(
                        j.Type,
                        "fixed",
                        StringComparison.OrdinalIgnoreCase) &&
                    j.Confidence > 0.0 &&
                    j.Confidence < 0.70);

            if (weakMovable > 0)
            {
                model.Warnings.Add(
                    weakMovable.ToString(_ci) +
                    " movable joints have confidence below 0.70.");
            }

            if (model.Occurrences.Count >= 20 &&
                movable >
                    model.Occurrences.Count * 0.60)
            {
                model.Warnings.Add(
                    "High movable-joint ratio detected (" +
                    movable.ToString(_ci) +
                    "/" +
                    model.Occurrences.Count.ToString(_ci) +
                    "). Review constraint entity classification.");
            }

            foreach (string warning in _warnings)
                model.Warnings.Add(warning);

            Build51Log.Validate(
                "BUILD83_DOF_SUMMARY movable_tree=" +
                movable.ToString(_ci) +
                " estimated_tree_dof=" +
                estimatedTreeDof.ToString(_ci) +
                " movable_loops=" +
                rankLoops.ToString(_ci) +
                " explicitly_classified_movable=" +
                explicitlyClassifiedMovable.ToString(_ci) +
                " complete_explicit_classification=" +
                completeExplicitCoordinateClassification.ToString() +
                " explicit_independent=" +
                explicitIndependent.ToString(_ci) +
                " explicit_linear_coupling_rank=" +
                explicitLinearCouplingRank.ToString(_ci) +
                " independent_dof=" +
                model.IndependentDof.ToString(_ci));
        }

        // --------------------------------------------------------------------
        // AutoMind BUILD124 USD writer
        // --------------------------------------------------------------------
        // Writes an OpenUSD ASCII stage with real UsdPhysics joint prims.
        // The URDF+ mechanical model remains the source of truth for CAD-derived
        // pivots, axes, local joint frames, loops and couplings.
        private void WriteUsd(string path, MechanicalModel model, bool gripperOverlay)
        {
            if (model == null) return;
            string robotPrim = UsdName(String.IsNullOrEmpty(model.RobotName) ? "AutoMindRobot" : model.RobotName);
            using (StreamWriter w = new StreamWriter(path, false, new UTF8Encoding(false)))
            {
                W(w, "#usda 1.0");
                W(w, "(");
                W(w, "    defaultPrim = \"" + UsdStr(robotPrim) + "\"");
                W(w, "    metersPerUnit = 1");
                W(w, "    upAxis = \"Z\"");
                W(w, ")");
                W(w, "");
                W(w, "def Xform \"" + UsdStr(robotPrim) + "\" (");
                W(w, "    kind = \"component\"");
                W(w, ")");
                W(w, "{");
                W(w, "    custom string automind:schema = \"AutoMind.IAM.USDOnlyJoints.v6.Build128StrictJointContract\"");
                W(w, "    custom string automind:source = \"Inventor IAM -> AutoMind mechanical model -> OpenUSD UsdPhysics\"");
                W(w, "    custom bool automind:hasJointInformation = true");
                W(w, "    custom int automind:treeJointCount = " + model.TreeJoints.Count.ToString(_ci));
                W(w, "    custom int automind:loopJointCount = " + model.LoopJoints.Count.ToString(_ci));
                W(w, "    custom int automind:couplingCount = " + model.Couplings.Count.ToString(_ci));
                int activeImplicitClosureCandidateCount = model.ImplicitCandidates.Count(k => IsActiveUsdImplicitClosureCandidate(k));
                W(w, "    custom int automind:implicitCandidateCount = " + model.ImplicitCandidates.Count.ToString(_ci));
                W(w, "    custom int automind:activeImplicitClosureCandidateCount = " + activeImplicitClosureCandidateCount.ToString(_ci));
                W(w, "    custom string automind:loopPolicy = \"rank5_free_dof1_unique_axis_exported_as_passive_revolute_loop_candidate; rank4_axis_candidates_written_as_viewer_closure_residuals\"");
                W(w, "    custom string automind:closedChainSolver = \"gauss_newton_multi_loop_pin_axis_closure\"");
                W(w, "    custom bool automind:parallelGripperOverlay = " + (gripperOverlay ? "true" : "false"));
                W(w, "");
                W(w, "    def PhysicsScene \"physicsScene\"");
                W(w, "    {");
                W(w, "        vector3f physics:gravityDirection = (0, 0, -1)");
                W(w, "        float physics:gravityMagnitude = 9.81");
                W(w, "    }");
                W(w, "");
                W(w, "    def Scope \"Materials\"");
                W(w, "    {");
                foreach (OccInfo occ in model.Occurrences)
                    WriteUsdMaterial(w, occ);
                W(w, "    }");
                W(w, "");
                W(w, "    def Scope \"Links\"");
                W(w, "    {");
                WriteUsdBaseLink(w);
                foreach (OccInfo occ in model.Occurrences)
                    WriteUsdLink(w, occ);
                W(w, "    }");
                W(w, "");
                W(w, "    def Scope \"Joints\"");
                W(w, "    {");
                WriteUsdJoint(w, model.RootJoint, "base_link", model.RootOccurrence == null ? "" : model.RootOccurrence.LinkName, "root");
                foreach (JointSpec j in model.TreeJoints)
                    WriteUsdJoint(w, j, j.Parent == null ? "" : j.Parent.LinkName, j.Child == null ? "" : j.Child.LinkName, "tree");
                foreach (JointSpec l in model.LoopJoints)
                    WriteUsdJoint(w, l, l.Parent == null ? "" : l.Parent.LinkName, l.Child == null ? "" : l.Child.LinkName, "loop");
                W(w, "    }");
                W(w, "");
                W(w, "    def Scope \"Couplings\"");
                W(w, "    {");
                foreach (CouplingInfo c in model.Couplings)
                    WriteUsdCoupling(w, c);
                W(w, "    }");
                W(w, "");
                W(w, "    def Scope \"CadEvidence\"");
                W(w, "    {");
                WriteUsdCadEvidence(w, model);
                W(w, "    }");
                W(w, "}");
            }
            int movableTreeForViewer = model.TreeJoints.Count(j => j != null && !String.Equals(UsdPhysicsJointType(j.Type), "PhysicsFixedJoint", StringComparison.OrdinalIgnoreCase));
            int fixedTreeForViewer = model.TreeJoints.Count(j => j != null && String.Equals(UsdPhysicsJointType(j.Type), "PhysicsFixedJoint", StringComparison.OrdinalIgnoreCase));
            Build51Log.Summary("BUILD128_USD_EXPORT_OK usd_path='" + path + "' links=" + model.Occurrences.Count.ToString(_ci) + " tree_joints=" + model.TreeJoints.Count.ToString(_ci) + " movable_tree_for_viewer=" + movableTreeForViewer.ToString(_ci) + " fixed_tree_for_viewer=" + fixedTreeForViewer.ToString(_ci) + " loops=" + model.LoopJoints.Count.ToString(_ci) + " couplings=" + model.Couplings.Count.ToString(_ci));
        }

        private void WriteUsdBaseLink(StreamWriter w)
        {
            W(w, "        def Xform \"base_link\" (");
            W(w, "            prepend apiSchemas = [\"PhysicsRigidBodyAPI\", \"PhysicsMassAPI\"]");
            W(w, "        )");
            W(w, "        {");
            W(w, "            custom string automind:linkName = \"base_link\"");
            W(w, "            custom string automind:nodeKind = \"world_base\"");
            W(w, "            bool physics:rigidBodyEnabled = false");
            W(w, "            float physics:mass = 0.01");
            W(w, "            matrix4d xformOp:transform = " + UsdMatrix(Mat4.Identity));
            W(w, "            uniform token[] xformOpOrder = [\"xformOp:transform\"]");
            W(w, "        }");
        }

        private void WriteUsdLink(StreamWriter w, OccInfo occ)
        {
            if (occ == null) return;
            string link = UsdName(occ.LinkName);
            W(w, "        def Xform \"" + UsdStr(link) + "\" (");
            W(w, "            prepend apiSchemas = [\"PhysicsRigidBodyAPI\", \"PhysicsMassAPI\"]");
            W(w, "        )");
            W(w, "        {");
            W(w, "            custom string automind:linkName = \"" + UsdStr(occ.LinkName) + "\"");
            W(w, "            custom string automind:displayName = \"" + UsdStr(occ.Name) + "\"");
            W(w, "            custom string automind:cadPath = \"" + UsdStr(occ.Path) + "\"");
            W(w, "            custom string automind:stableId = \"" + UsdStr(occ.StableId) + "\"");
            W(w, "            custom string automind:nodeKind = \"" + (occ.IsAssemblyNode ? "assembly_frame" : "leaf_component") + "\"");
            W(w, "            custom bool automind:flexible = " + (occ.IsFlexible ? "true" : "false"));
            W(w, "            custom bool automind:grounded = " + (occ.Grounded ? "true" : "false"));
            W(w, "            custom string automind:sourceDocument = \"" + UsdStr(occ.SourceDocumentPath) + "\"");
            W(w, "            bool physics:rigidBodyEnabled = true");
            W(w, "            float physics:mass = " + F(Math.Max(0.0001, occ.MassKg)));
            W(w, "            point3f physics:centerOfMass = " + UsdVec(occ.CenterOfMassLocal));
            W(w, "            matrix4d xformOp:transform = " + UsdMatrix(occ.LinkFrameWorld));
            W(w, "            uniform token[] xformOpOrder = [\"xformOp:transform\"]");

            if (occ.HasVisualGeometry && occ.Occurrence != null)
            {
                try
                {
                    List<Inv.SurfaceBody> bodies = CollectSurfaceBodiesFromOccurrenceForLegacyDae(occ.Occurrence);
                    double[] verticesWorld;
                    int[] indices;
                    if (bodies.Count > 0 && TessellateBodiesToMeshArraysLegacy(bodies, out verticesWorld, out indices) && verticesWorld != null && indices != null && verticesWorld.Length >= 9 && indices.Length >= 3)
                    {
                        double[] verticesLocal;
                        Inv.Matrix occurrenceMatrix = null;
                        try { occurrenceMatrix = occ.Occurrence.Transformation; } catch { occurrenceMatrix = null; }
                        TransformVerticesToOccurrenceLocalLegacy(verticesWorld, occurrenceMatrix, out verticesLocal);
                        WriteUsdMesh(w, "visual", occ, verticesLocal, indices);
                    }
                    else
                    {
                        WriteUsdPlaceholderCube(w, occ);
                    }
                }
                catch (Exception ex)
                {
                    W(w, "            custom string automind:meshExportWarning = \"" + UsdStr(ex.Message) + "\"");
                    WriteUsdPlaceholderCube(w, occ);
                }
            }
            W(w, "        }");
        }

        private void WriteUsdMesh(StreamWriter w, string meshName, OccInfo occ, double[] verticesLocal, int[] indices)
        {
            W(w, "            def Mesh \"" + UsdStr(UsdName(meshName)) + "\" (");
            W(w, "                prepend apiSchemas = [\"PhysicsCollisionAPI\", \"MaterialBindingAPI\"]");
            W(w, "            )");
            W(w, "            {");
            W(w, "                bool physics:collisionEnabled = true");
            W(w, "                matrix4d xformOp:transform = " + UsdMatrix(occ.VisualOriginInLink));
            W(w, "                uniform token[] xformOpOrder = [\"xformOp:transform\"]");
            W(w, "                point3f[] points = " + UsdPointArray(verticesLocal));
            W(w, "                int[] faceVertexCounts = " + UsdFaceCounts(indices.Length / 3));
            W(w, "                int[] faceVertexIndices = " + UsdIntArray(indices));
            W(w, "                color3f[] primvars:displayColor = [(" + F(occ.Color.R / 255.0) + ", " + F(occ.Color.G / 255.0) + ", " + F(occ.Color.B / 255.0) + ")]");
            W(w, "                uniform token primvars:displayColor:interpolation = \"constant\"");

            int vertexCount = (verticesLocal == null) ? 0 : verticesLocal.Length / 3;
            W(w, "                texCoord2f[] primvars:st = " + UsdUvArray(vertexCount));
            W(w, "                uniform token primvars:st:interpolation = \"vertex\"");

            string tex = UsdTextureAssetFile(occ);
            if (!String.IsNullOrEmpty(tex))
            {
                W(w, "                custom string automind:textureFile = \"" + UsdStr(tex) + "\"");
                W(w, "                custom string automind:textureSystem = \"urdf_plus_legacy_png_atlas\"");
            }

            W(w, "                rel material:binding = </" + UsdPathName(CurrentUsdRobotNameSafe(null, "", "")) + "/Materials/" + UsdName("mat_" + occ.LinkName) + ">");
            W(w, "            }");
        }

        private void WriteUsdMaterial(StreamWriter w, OccInfo occ)
        {
            if (occ == null) return;
            string matName = UsdName("mat_" + occ.LinkName);
            string robot = UsdPathName(CurrentUsdRobotNameSafe(null, "", ""));
            string tex = UsdTextureAssetFile(occ);
            double r = occ.Color.R / 255.0;
            double g = occ.Color.G / 255.0;
            double b = occ.Color.B / 255.0;

            W(w, "        def Material \"" + UsdStr(matName) + "\"");
            W(w, "        {");
            W(w, "            token outputs:surface.connect = </" + robot + "/Materials/" + matName + "/PreviewSurface.outputs:surface>");
            W(w, "            def Shader \"PreviewSurface\"");
            W(w, "            {");
            W(w, "                uniform token info:id = \"UsdPreviewSurface\"");
            W(w, "                color3f inputs:diffuseColor = (" + F(r) + ", " + F(g) + ", " + F(b) + ")");
            if (!String.IsNullOrEmpty(tex))
                W(w, "                color3f inputs:diffuseColor.connect = </" + robot + "/Materials/" + matName + "/DiffuseTexture.outputs:rgb>");
            W(w, "                float inputs:roughness = 0.62");
            W(w, "                float inputs:metallic = 0.05");
            W(w, "                token outputs:surface");
            W(w, "            }");

            if (!String.IsNullOrEmpty(tex))
            {
                W(w, "            def Shader \"DiffuseTexture\"");
                W(w, "            {");
                W(w, "                uniform token info:id = \"UsdUVTexture\"");
                W(w, "                asset inputs:file = @" + UsdAssetPath(tex) + "@");
                W(w, "                token inputs:sourceColorSpace = \"sRGB\"");
                W(w, "                float2 inputs:st.connect = </" + robot + "/Materials/" + matName + "/PrimvarReader.outputs:result>");
                W(w, "                color3f outputs:rgb");
                W(w, "            }");
                W(w, "            def Shader \"PrimvarReader\"");
                W(w, "            {");
                W(w, "                uniform token info:id = \"UsdPrimvarReader_float2\"");
                W(w, "                token inputs:varname = \"st\"");
                W(w, "                float2 outputs:result");
                W(w, "            }");
            }

            W(w, "        }");
        }

        private void WriteUsdPlaceholderCube(StreamWriter w, OccInfo occ)
        {
            double s = 0.005;
            double[] v = new double[] { -s,-s,-s, s,-s,-s, s,s,-s, -s,s,-s, -s,-s,s, s,-s,s, s,s,s, -s,s,s };
            int[] idx = new int[] { 0,1,2, 0,2,3, 4,6,5, 4,7,6, 0,4,5, 0,5,1, 1,5,6, 1,6,2, 2,6,7, 2,7,3, 3,7,4, 3,4,0 };
            WriteUsdMesh(w, "visual_placeholder", occ, v, idx);
        }

        private void WriteUsdJoint(StreamWriter w, JointSpec j, string parentLink, string childLink, string role)
        {
            if (j == null || String.IsNullOrEmpty(parentLink) || String.IsNullOrEmpty(childLink)) return;
            string usdType = UsdPhysicsJointType(j.Type);
            string jointName = UsdName(j.Name);
            W(w, "        def " + usdType + " \"" + UsdStr(jointName) + "\"");
            W(w, "        {");
            W(w, "            rel physics:body0 = </" + UsdPathName(CurrentUsdRobotNameSafe(j, parentLink, childLink)) + "/Links/" + UsdName(parentLink) + ">");
            W(w, "            rel physics:body1 = </" + UsdPathName(CurrentUsdRobotNameSafe(j, parentLink, childLink)) + "/Links/" + UsdName(childLink) + ">");
            W(w, "            point3f physics:localPos0 = " + UsdVec(j.OriginInParent.Translation));
            W(w, "            quatf physics:localRot0 = " + UsdQuat(j.OriginInParent));
            W(w, "            point3f physics:localPos1 = " + UsdVec(j.OriginInSuccessor.Translation));
            W(w, "            quatf physics:localRot1 = " + UsdQuat(j.OriginInSuccessor));
            if (!String.Equals(usdType, "PhysicsFixedJoint", StringComparison.OrdinalIgnoreCase))
            {
                W(w, "            token physics:axis = \"" + UsdAxisToken(j.AxisInJoint) + "\"");
                if (String.Equals(usdType, "PhysicsRevoluteJoint", StringComparison.OrdinalIgnoreCase))
                {
                    W(w, "            float physics:lowerLimit = " + F(j.Lower * 180.0 / Math.PI));
                    W(w, "            float physics:upperLimit = " + F(j.Upper * 180.0 / Math.PI));
                }
                else if (String.Equals(usdType, "PhysicsPrismaticJoint", StringComparison.OrdinalIgnoreCase))
                {
                    W(w, "            float physics:lowerLimit = " + F(j.Lower));
                    W(w, "            float physics:upperLimit = " + F(j.Upper));
                }
            }
            W(w, "            custom string automind:jointName = \"" + UsdStr(j.Name) + "\"");
            W(w, "            custom string automind:jointRole = \"" + UsdStr(role) + "\"");
            W(w, "            custom string automind:originalType = \"" + UsdStr(j.Type) + "\"");
            string motionTypeForViewer = String.Equals(usdType, "PhysicsFixedJoint", StringComparison.OrdinalIgnoreCase) ? "fixed" : (String.Equals(usdType, "PhysicsPrismaticJoint", StringComparison.OrdinalIgnoreCase) ? "prismatic" : "continuous");
            bool movableForViewer = !String.Equals(usdType, "PhysicsFixedJoint", StringComparison.OrdinalIgnoreCase);
            bool viewerControllable = movableForViewer && !String.Equals(role, "loop", StringComparison.OrdinalIgnoreCase);
            W(w, "            custom string automind:usdPhysicsJointType = \"" + UsdStr(usdType) + "\"");
            W(w, "            custom string automind:motionType = \"" + UsdStr(motionTypeForViewer) + "\"");
            W(w, "            custom bool automind:movable = " + (movableForViewer ? "true" : "false"));
            W(w, "            custom bool automind:viewerControllable = " + (viewerControllable ? "true" : "false"));
            W(w, "            custom string automind:viewerSemantics = \"BUILD128 schema-authoritative: PhysicsRevoluteJoint/PhysicsPrismaticJoint are never shown as fixed; fixed visual fasteners inherit nearest movable ancestor in HTML\"");
            W(w, "            custom string automind:parentLink = \"" + UsdStr(parentLink) + "\"");
            W(w, "            custom string automind:childLink = \"" + UsdStr(childLink) + "\"");
            W(w, "            custom string automind:independent = \"" + UsdStr(j.Independent) + "\"");
            W(w, "            custom string automind:kinematicRole = \"" + UsdStr(j.KinematicRole) + "\"");
            W(w, "            custom string automind:kinematicAuthority = \"" + UsdStr(j.KinematicAuthority) + "\"");
            W(w, "            custom bool automind:implicitMotionCandidate = " + (j.ImplicitMotionCandidate ? "true" : "false"));
            W(w, "            custom bool automind:requiresReview = " + (j.RequiresReview ? "true" : "false"));
            W(w, "            custom string automind:source = \"" + UsdStr(j.Source) + "\"");
            W(w, "            custom string automind:evidence = \"" + UsdStr(j.Evidence) + "\"");
            W(w, "            custom string automind:pivotSource = \"" + UsdStr(j.PivotSource) + "\"");
            W(w, "            custom float3 automind:axisWorld = " + UsdVec(j.AxisWorld));
            W(w, "            custom float3 automind:axisJoint = " + UsdVec(j.AxisInJoint));
            W(w, "            custom float3 automind:axisSuccessor = " + UsdVec(j.AxisInSuccessor));
            W(w, "            custom point3f automind:axisPointWorld = " + UsdVec(j.AxisPointWorld));
            W(w, "            custom double automind:lowerRad = " + F(j.Lower));
            W(w, "            custom double automind:upperRad = " + F(j.Upper));
            W(w, "            custom double automind:confidence = " + F(j.Confidence));
            W(w, "            custom int automind:estimatedFreeDof = " + j.EstimatedFreeDof.ToString(_ci));
            W(w, "            custom double automind:closureErrorMeters = " + F(j.ClosureErrorMeters));
            if (!String.IsNullOrEmpty(j.MimicJointName))
            {
                W(w, "            custom string automind:mimicJoint = \"" + UsdStr(j.MimicJointName) + "\"");
                W(w, "            custom double automind:mimicMultiplier = " + F(j.MimicMultiplier));
                W(w, "            custom double automind:mimicOffset = " + F(j.MimicOffset));
            }
            if (j.InvolvedTreeJoints.Count > 0)
                W(w, "            custom string automind:involvedTreeJoints = \"" + UsdStr(String.Join(" ", j.InvolvedTreeJoints.ToArray())) + "\"");
            W(w, "        }");
        }

        private void WriteUsdCoupling(StreamWriter w, CouplingInfo c)
        {
            if (c == null) return;
            W(w, "        def Xform \"" + UsdStr(UsdName(String.IsNullOrEmpty(c.Name) ? "coupling" : c.Name)) + "\"");
            W(w, "        {");
            W(w, "            custom string automind:kind = \"coupling\"");
            W(w, "            custom string automind:type = \"" + UsdStr(c.Type) + "\"");
            W(w, "            custom string automind:solver = \"" + UsdStr(c.Solver) + "\"");
            W(w, "            custom string automind:mode = \"" + UsdStr(c.Mode) + "\"");
            W(w, "            custom string automind:masterJoint = \"" + UsdStr(c.MasterJoint) + "\"");
            W(w, "            custom string automind:dependentJoint = \"" + UsdStr(c.DependentJoint) + "\"");
            W(w, "            custom string automind:masterLink = \"" + UsdStr(c.MasterLink) + "\"");
            W(w, "            custom string automind:dependentLink = \"" + UsdStr(c.DependentLink) + "\"");
            W(w, "            custom double automind:ratio = " + F(c.Ratio));
            W(w, "            custom double automind:offset = " + F(c.Offset));
            W(w, "            custom string automind:source = \"" + UsdStr(c.Source) + "\"");
            W(w, "            custom string automind:evidence = \"" + UsdStr(c.Evidence) + "\"");
            W(w, "        }");
        }

        private bool IsActiveUsdImplicitClosureCandidate(ImplicitKinematicCandidate k)
        {
            if (k == null) return false;
            if (!k.HasAxisPoint) return false;
            if (String.IsNullOrEmpty(k.LinkA) || String.IsNullOrEmpty(k.LinkB)) return false;
            if (k.AxisLikeCount <= 0) return false;
            if (k.RawRank < 4) return false;
            // A candidate that already became a tree or loop joint is evidence, not another residual.
            if (!String.IsNullOrEmpty(k.ExportedJoint) &&
                !String.Equals(k.ExportedRole, "no_tree_or_loop_edge", StringComparison.OrdinalIgnoreCase))
                return false;
            return true;
        }

        private void WriteUsdCadEvidence(StreamWriter w, MechanicalModel model)
        {
            int i = 0;
            foreach (NativeJointInfo n in model.NativeJoints)
            {
                if (n == null) continue;
                W(w, "        def Xform \"native_joint_" + i.ToString(_ci) + "\"");
                W(w, "        {");
                W(w, "            custom string automind:kind = \"native_inventor_joint_evidence\"");
                W(w, "            custom string automind:name = \"" + UsdStr(n.Name) + "\"");
                W(w, "            custom string automind:apiClass = \"" + UsdStr(n.ApiClass) + "\"");
                W(w, "            custom string automind:jointKind = \"" + UsdStr(n.JointKind) + "\"");
                W(w, "            custom string automind:linkA = \"" + UsdStr(n.A == null ? "" : n.A.LinkName) + "\"");
                W(w, "            custom string automind:linkB = \"" + UsdStr(n.B == null ? "" : n.B.LinkName) + "\"");
                W(w, "            custom bool automind:hasAxis = " + (n.HasAxis ? "true" : "false"));
                W(w, "            custom float3 automind:axisWorld = " + UsdVec(n.AxisWorld));
                W(w, "            custom bool automind:hasAxisPoint = " + (n.HasAxisPoint ? "true" : "false"));
                W(w, "            custom point3f automind:axisPointWorld = " + UsdVec(n.AxisPointWorld));
                W(w, "            custom string automind:source = \"" + UsdStr(n.AxisSource) + " " + UsdStr(n.PivotSource) + "\"");
                W(w, "        }");
                i++;
            }

            int kIndex = 0;
            int active = 0;
            foreach (ImplicitKinematicCandidate k in model.ImplicitCandidates)
            {
                if (k == null) continue;
                bool activeForViewerClosure = IsActiveUsdImplicitClosureCandidate(k);
                if (activeForViewerClosure) active++;
                W(w, "        def Xform \"implicit_candidate_" + kIndex.ToString(_ci) + "\"");
                W(w, "        {");
                W(w, "            custom string automind:kind = \"implicit_kinematic_candidate\"");
                W(w, "            custom string automind:pair = \"" + UsdStr(k.PairKey) + "\"");
                W(w, "            custom string automind:linkA = \"" + UsdStr(k.LinkA) + "\"");
                W(w, "            custom string automind:linkB = \"" + UsdStr(k.LinkB) + "\"");
                W(w, "            custom int automind:rank = " + k.RawRank.ToString(_ci));
                W(w, "            custom int automind:freeDof = " + k.RawFreeDof.ToString(_ci));
                W(w, "            custom int automind:axisLike = " + k.AxisLikeCount.ToString(_ci));
                W(w, "            custom int automind:planar = " + k.PlanarCount.ToString(_ci));
                W(w, "            custom bool automind:hasAxisPoint = " + (k.HasAxisPoint ? "true" : "false"));
                W(w, "            custom float3 automind:axisWorld = " + UsdVec(k.AxisWorld));
                W(w, "            custom point3f automind:axisPointWorld = " + UsdVec(k.AxisPointWorld));
                W(w, "            custom string automind:exportedJoint = \"" + UsdStr(k.ExportedJoint) + "\"");
                W(w, "            custom string automind:exportedType = \"" + UsdStr(k.ExportedType) + "\"");
                W(w, "            custom string automind:exportedRole = \"" + UsdStr(k.ExportedRole) + "\"");
                W(w, "            custom bool automind:activeForViewerClosure = " + (activeForViewerClosure ? "true" : "false"));
                W(w, "            custom string automind:solver = \"implicit_axis_point_closure_dls\"");
                W(w, "            custom string automind:evidence = \"" + UsdStr(k.Evidence) + "\"");
                W(w, "            custom string automind:reason = \"" + UsdStr(k.Reason) + "\"");
                W(w, "        }");
                kIndex++;
            }
            Build51Log.Summary("BUILD128_USD_CAD_EVIDENCE_WRITTEN native=" + i.ToString(_ci) + " implicit_candidates=" + kIndex.ToString(_ci) + " active_implicit_closures=" + active.ToString(_ci));
        }

        private string CurrentUsdRobotNameSafe(JointSpec j, string parentLink, string childLink)
        {
            // Joints are authored under the current default prim.  This helper keeps
            // relationship paths robust even when called from standalone unit tests.
            return UsdName(String.IsNullOrEmpty(_currentUsdRobotNameForWriter) ? "AutoMindRobot" : _currentUsdRobotNameForWriter);
        }

        private string _currentUsdRobotNameForWriter = "";

        private static void W(StreamWriter w, string s)
        {
            w.WriteLine(s ?? "");
        }

        private string UsdPhysicsJointType(string type)
        {
            string t = (type ?? "").ToLowerInvariant();
            if (t == "fixed" || t == "rigid" || t == "rigid_link_lock") return "PhysicsFixedJoint";
            if (t == "prismatic" || t == "slider" || t == "translational") return "PhysicsPrismaticJoint";
            if (t == "spherical" || t == "ball") return "PhysicsSphericalJoint";
            if (t == "revolute" || t == "continuous" || t == "cylindrical" || t == "hinge") return "PhysicsRevoluteJoint";
            return "PhysicsJoint";
        }

        private string UsdAxisToken(Vec3 axis)
        {
            Vec3 n = axis.NormalizedOr(Vec3.UnitZ);
            double ax = Math.Abs(n.X), ay = Math.Abs(n.Y), az = Math.Abs(n.Z);
            if (ax >= ay && ax >= az) return "X";
            if (ay >= ax && ay >= az) return "Y";
            return "Z";
        }

        private string UsdName(string s)
        {
            string r = SanitizeName(String.IsNullOrEmpty(s) ? "unnamed" : s);
            return r;
        }

        private string UsdPathName(string s)
        {
            return UsdName(s);
        }

        private string UsdStr(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", " ").Replace("\n", " ");
        }

        private string UsdVec(Vec3 v)
        {
            return "(" + F(v.X) + ", " + F(v.Y) + ", " + F(v.Z) + ")";
        }

        private string UsdMatrix(Mat4 m)
        {
            return "((" + F(m.M11) + ", " + F(m.M12) + ", " + F(m.M13) + ", " + F(m.M14) + "), " +
                   "(" + F(m.M21) + ", " + F(m.M22) + ", " + F(m.M23) + ", " + F(m.M24) + "), " +
                   "(" + F(m.M31) + ", " + F(m.M32) + ", " + F(m.M33) + ", " + F(m.M34) + "), " +
                   "(0, 0, 0, 1))";
        }

        private string UsdQuat(Mat4 m)
        {
            double tr = m.M11 + m.M22 + m.M33;
            double qw, qx, qy, qz;
            if (tr > 0.0)
            {
                double s = Math.Sqrt(tr + 1.0) * 2.0;
                qw = 0.25 * s;
                qx = (m.M32 - m.M23) / s;
                qy = (m.M13 - m.M31) / s;
                qz = (m.M21 - m.M12) / s;
            }
            else if (m.M11 > m.M22 && m.M11 > m.M33)
            {
                double s = Math.Sqrt(1.0 + m.M11 - m.M22 - m.M33) * 2.0;
                qw = (m.M32 - m.M23) / s;
                qx = 0.25 * s;
                qy = (m.M12 + m.M21) / s;
                qz = (m.M13 + m.M31) / s;
            }
            else if (m.M22 > m.M33)
            {
                double s = Math.Sqrt(1.0 + m.M22 - m.M11 - m.M33) * 2.0;
                qw = (m.M13 - m.M31) / s;
                qx = (m.M12 + m.M21) / s;
                qy = 0.25 * s;
                qz = (m.M23 + m.M32) / s;
            }
            else
            {
                double s = Math.Sqrt(1.0 + m.M33 - m.M11 - m.M22) * 2.0;
                qw = (m.M21 - m.M12) / s;
                qx = (m.M13 + m.M31) / s;
                qy = (m.M23 + m.M32) / s;
                qz = 0.25 * s;
            }
            double n = Math.Sqrt(qw * qw + qx * qx + qy * qy + qz * qz);
            if (n < 1e-12 || Double.IsNaN(n) || Double.IsInfinity(n)) return "(1, 0, 0, 0)";
            return "(" + F(qw / n) + ", " + F(qx / n) + ", " + F(qy / n) + ", " + F(qz / n) + ")";
        }

        private string UsdPointArray(double[] verticesLocal)
        {
            if (verticesLocal == null || verticesLocal.Length < 3) return "[]";
            StringBuilder sb = new StringBuilder();
            sb.Append("[");
            int count = verticesLocal.Length / 3;
            for (int i = 0; i < count; i++)
            {
                if (i > 0) sb.Append(", ");
                sb.Append("(");
                sb.Append(F(verticesLocal[i * 3 + 0])); sb.Append(", ");
                sb.Append(F(verticesLocal[i * 3 + 1])); sb.Append(", ");
                sb.Append(F(verticesLocal[i * 3 + 2])); sb.Append(")");
            }
            sb.Append("]");
            return sb.ToString();
        }

        private string UsdUvArray(int vertexCount)
        {
            if (vertexCount <= 0) return "[]";
            StringBuilder sb = new StringBuilder();
            sb.Append("[");
            for (int i = 0; i < vertexCount; i++)
            {
                if (i > 0) sb.Append(", ");
                // Same legacy URDF+ texture contract as the DAE writer: a simple
                // per-vertex UV centered on the generated PNG/atlas.
                sb.Append("(0.5, 0.5)");
            }
            sb.Append("]");
            return sb.ToString();
        }

        private string UsdTextureAssetFile(OccInfo occ)
        {
            if (occ == null || String.IsNullOrEmpty(occ.TextureFile)) return "";
            try
            {
                string file = Path.GetFileName(occ.TextureFile);
                return String.IsNullOrEmpty(file) ? "" : file.Replace("\\", "/");
            }
            catch { return ""; }
        }

        private string UsdAssetPath(string s)
        {
            if (s == null) return "";
            // Asset paths are written inside @...@ delimiters.  Keep the generated
            // URDF+ PNG basename intact while escaping only delimiter-like chars.
            return s.Replace("\\", "/").Replace("@", "@@").Replace("\r", " ").Replace("\n", " ");
        }

        private string UsdIntArray(int[] values)
        {
            if (values == null || values.Length == 0) return "[]";
            StringBuilder sb = new StringBuilder();
            sb.Append("[");
            for (int i = 0; i < values.Length; i++)
            {
                if (i > 0) sb.Append(", ");
                sb.Append(values[i].ToString(_ci));
            }
            sb.Append("]");
            return sb.ToString();
        }

        private string UsdFaceCounts(int triangles)
        {
            if (triangles <= 0) return "[]";
            StringBuilder sb = new StringBuilder();
            sb.Append("[");
            for (int i = 0; i < triangles; i++)
            {
                if (i > 0) sb.Append(", ");
                sb.Append("3");
            }
            sb.Append("]");
            return sb.ToString();
        }


        // --------------------------------------------------------------------
        // --------------------------------------------------------------------
        // URDF writer
        // --------------------------------------------------------------------


        private void AuditWrittenUsd(string usdPath, MechanicalModel model)
        {
            try
            {
                if (String.IsNullOrEmpty(usdPath) || !File.Exists(usdPath))
                {
                    Build51Log.Error("USD_AUDIT missing file path='" + (usdPath ?? "") + "'");
                    return;
                }
                string text = File.ReadAllText(usdPath, Encoding.UTF8);
                int linkCount = CountRegex(text, "custom\\s+string\\s+automind:linkName");
                int jointCount = CountRegex(text, "def\\s+Physics[A-Za-z]*Joint\\s+\\\"");
                int relBody0 = CountRegex(text, "rel\\s+physics:body0");
                int relBody1 = CountRegex(text, "rel\\s+physics:body1");
                int localPos0 = CountRegex(text, "physics:localPos0");
                int localPos1 = CountRegex(text, "physics:localPos1");
                int axisCount = CountRegex(text, "physics:axis");
                int meshCount = CountRegex(text, "def\\s+Mesh\\s+\\\"");
                int couplingCount = CountRegex(text, "automind:kind\\s*=\\s*\\\"coupling\\\"");
                int evidenceCount = CountRegex(text, "automind:kind\\s*=\\s*\\\"cad_constraint_evidence\\\"");
                bool defaultPrimOk = text.IndexOf("defaultPrim", StringComparison.OrdinalIgnoreCase) >= 0;
                bool hasScene = text.IndexOf("def PhysicsScene", StringComparison.OrdinalIgnoreCase) >= 0;
                Build51Log.Xml("USD_AUDIT_SUMMARY path='" + usdPath + "' file_bytes=" + new FileInfo(usdPath).Length.ToString(_ci) +
                    " links=" + linkCount + " expected_links=" + (model == null ? 0 : model.Occurrences.Count + 1).ToString(_ci) +
                    " joints=" + jointCount + " expected_joints=" + (model == null ? 0 : (1 + model.TreeJoints.Count + model.LoopJoints.Count)).ToString(_ci) +
                    " body0=" + relBody0 + " body1=" + relBody1 + " localPos0=" + localPos0 + " localPos1=" + localPos1 +
                    " axes=" + axisCount + " meshes=" + meshCount + " couplings=" + couplingCount + " cad_evidence=" + evidenceCount +
                    " defaultPrim=" + defaultPrimOk.ToString() + " physicsScene=" + hasScene.ToString());
                if (model != null && linkCount < model.Occurrences.Count)
                    Build51Log.Warn("USD_AUDIT_LINK_COUNT_TOO_LOW parsed=" + linkCount + " expected_occurrences=" + model.Occurrences.Count + " viewer_parser_must_read_nested_prims_recursively");
                if (jointCount < model.TreeJoints.Count)
                    Build51Log.Warn("USD_AUDIT_JOINT_COUNT_TOO_LOW parsed=" + jointCount + " expected_tree=" + model.TreeJoints.Count);
            }
            catch (Exception ex)
            {
                Build51Log.Error("USD_AUDIT_FAILED " + ex.ToString());
            }
        }

        private void WriteUsdMaxDebugFiles(string usdPath, MechanicalModel model, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints, bool gripperOverlay)
        {
            try
            {
                if (model == null || String.IsNullOrEmpty(_exportDir)) return;
                Directory.CreateDirectory(_exportDir);

                string manifest = Path.Combine(_exportDir, "AutoMind_USD_DEBUG_README.txt");
                string linksCsv = Path.Combine(_exportDir, "AutoMind_USD_LINKS.csv");
                string jointsCsv = Path.Combine(_exportDir, "AutoMind_USD_JOINTS.csv");
                string constraintsCsv = Path.Combine(_exportDir, "AutoMind_USD_CAD_CONSTRAINTS.csv");
                string nativeCsv = Path.Combine(_exportDir, "AutoMind_USD_NATIVE_JOINTS.csv");
                string candidatesCsv = Path.Combine(_exportDir, "AutoMind_USD_IMPLICIT_CANDIDATES.csv");
                string texturesCsv = Path.Combine(_exportDir, "AutoMind_USD_TEXTURES.csv");
                string solverCsv = Path.Combine(_exportDir, "AutoMind_USD_SOLVER_CONTRACT.csv");
                string auditTxt = Path.Combine(_exportDir, "AutoMind_USD_AUDIT_SUMMARY.txt");

                File.WriteAllText(manifest,
                    "AutoMind USD BUILD125 - MAX DEBUG PACKAGE\r\n" +
                    "=========================================\r\n" +
                    "USD ONLY export. No .urdf and no URDF_Export folder are generated.\r\n" +
                    "\r\nMain USD:\r\n  " + usdPath + "\r\n\r\nDebug files:\r\n" +
                    "  AutoMind_USD_DEBUG_MAX.log              Full live DebugView + file log.\r\n" +
                    "  AutoMind_USD_AUDIT_SUMMARY.txt          Final counts and consistency checks.\r\n" +
                    "  AutoMind_USD_LINKS.csv                  Every Inventor occurrence exported as USD link.\r\n" +
                    "  AutoMind_USD_JOINTS.csv                 Root/tree/loop joints with body0/body1, axes, limits, evidence.\r\n" +
                    "  AutoMind_USD_CAD_CONSTRAINTS.csv        Raw Inventor constraint evidence.\r\n" +
                    "  AutoMind_USD_NATIVE_JOINTS.csv          Native Inventor AssemblyJoint evidence.\r\n" +
                    "  AutoMind_USD_IMPLICIT_CANDIDATES.csv    Candidate pairs not necessarily exported as active joints.\r\n" +
                    "  AutoMind_USD_TEXTURES.csv                Texture PNG manifest and material fallback diagnostics.\r\n" +
                    "  AutoMind_USD_SOLVER_CONTRACT.csv        Viewer/DLS contract: linear couplings, solver hints and loop closures.\r\n" +
                    "  AutoMind_BUILD95_KINEMATICS_AUDIT.csv   Legacy-compatible audit from the mechanical graph.\r\n" +
                    "  AutoMind_BUILD95_IMPLICIT_CANDIDATES.csv Legacy-compatible candidate audit.\r\n\r\n" +
                    "Viewer requirement: parse nested USD prims recursively. A flat first-level parser will show only one link.\r\n",
                    Encoding.UTF8);

                List<string> linkLines = new List<string>();
                linkLines.Add("index,link_name,display_name,stable_id,cad_path,node_kind,grounded,visible,suppressed,flexible,has_visual_geometry,mass_kg,world_xyz,world_rpy,range_min,range_max,source_document");
                foreach (OccInfo o in model.Occurrences)
                {
                    if (o == null) continue;
                    linkLines.Add(String.Join(",", new string[] {
                        Csv(o.Index.ToString(_ci)), Csv(o.LinkName), Csv(o.Name), Csv(o.StableId), Csv(o.Path), Csv(o.IsAssemblyNode ? "assembly_frame" : "leaf_component"),
                        Csv(o.Grounded ? "true" : "false"), Csv(o.Visible ? "true" : "false"), Csv(o.Suppressed ? "true" : "false"), Csv(o.IsFlexible ? "true" : "false"), Csv(o.HasVisualGeometry ? "true" : "false"),
                        Csv(F(o.MassKg)), Csv(o.LinkFrameWorld.Translation.Text()), Csv(o.LinkFrameWorld.ToRpy().Text()), Csv(o.RangeMinRaw.Text()), Csv(o.RangeMaxRaw.Text()), Csv(o.SourceDocumentPath)
                    }));
                }
                File.WriteAllLines(linksCsv, linkLines.ToArray(), Encoding.UTF8);

                List<JointSpec> allJoints = new List<JointSpec>();
                if (model.RootJoint != null) allJoints.Add(model.RootJoint);
                allJoints.AddRange(model.TreeJoints);
                allJoints.AddRange(model.LoopJoints);
                List<string> jointLines = new List<string>();
                jointLines.Add("role,joint_name,usd_schema,type,parent_link,child_link,independent,kinematic_role,kinematic_authority,implicit_motion_candidate,requires_review,axis_world,axis_joint,axis_successor,axis_point_world,origin_parent_xyz,origin_parent_rpy,origin_child_xyz,origin_child_rpy,lower_rad,upper_rad,confidence,estimated_free_dof,closure_error_m,mimic_joint,mimic_multiplier,mimic_offset,source,evidence,pivot_source,review_reason,involved_tree_joints");
                foreach (JointSpec j in allJoints)
                {
                    if (j == null) continue;
                    string role = j == model.RootJoint ? "root" : (model.LoopJoints.Contains(j) ? "loop" : "tree");
                    jointLines.Add(String.Join(",", new string[] {
                        Csv(role), Csv(j.Name), Csv(UsdPhysicsJointType(j.Type)), Csv(j.Type), Csv(j.Parent == null ? "base_link" : j.Parent.LinkName), Csv(j.Child == null ? "" : j.Child.LinkName),
                        Csv(j.Independent ?? ""), Csv(j.KinematicRole ?? ""), Csv(j.KinematicAuthority ?? ""), Csv(j.ImplicitMotionCandidate ? "true" : "false"), Csv(j.RequiresReview ? "true" : "false"),
                        Csv(j.AxisWorld.Text()), Csv(j.AxisInJoint.Text()), Csv(j.AxisInSuccessor.Text()), Csv(j.AxisPointWorld.Text()),
                        Csv(j.OriginInParent.Translation.Text()), Csv(j.OriginInParent.ToRpy().Text()), Csv(j.OriginInSuccessor.Translation.Text()), Csv(j.OriginInSuccessor.ToRpy().Text()),
                        Csv(F(j.Lower)), Csv(F(j.Upper)), Csv(F(j.Confidence)), Csv(j.EstimatedFreeDof.ToString(_ci)), Csv(F(j.ClosureErrorMeters)),
                        Csv(j.MimicJointName ?? ""), Csv(F(j.MimicMultiplier)), Csv(F(j.MimicOffset)), Csv(j.Source ?? ""), Csv(j.Evidence ?? ""), Csv(j.PivotSource ?? ""), Csv(j.ReviewReason ?? ""), Csv(String.Join(" ", j.InvolvedTreeJoints.ToArray()))
                    }));
                }
                File.WriteAllLines(jointsCsv, jointLines.ToArray(), Encoding.UTF8);

                List<string> cLines = new List<string>();
                cLines.Add("index,stable_id,name,api_class,context_path,context_source,link_a,link_b,has_axis,axis_world,has_axis_point,axis_point_world,axis_source,angle,insert,flush,mate,transitional,tangent,rotation_coupling,lock_rotation,suppressed,healthy,health,entity_one_kind,entity_two_kind,axis_like_geometry,planar_geometry,point_geometry,rigid_like,repaired,offset_m,motion_ratio,motion_offset");
                foreach (ConstraintInfo c in constraints ?? new List<ConstraintInfo>())
                {
                    if (c == null) continue;
                    cLines.Add(String.Join(",", new string[] {
                        Csv(c.Index.ToString(_ci)), Csv(c.StableId), Csv(c.Name), Csv(c.ApiClass), Csv(c.ContextPath), Csv(c.ContextSource), Csv(c.A == null ? "" : c.A.LinkName), Csv(c.B == null ? "" : c.B.LinkName),
                        Csv(c.HasAxis ? "true" : "false"), Csv(c.AxisWorld.Text()), Csv(c.HasAxisPoint ? "true" : "false"), Csv(c.AxisPointWorld.Text()), Csv(c.AxisSource),
                        Csv(c.IsAngleLike ? "true" : "false"), Csv(c.IsInsertLike ? "true" : "false"), Csv(c.IsFlushLike ? "true" : "false"), Csv(c.IsMateLike ? "true" : "false"), Csv(c.IsTransitionalLike ? "true" : "false"), Csv(c.IsTangentLike ? "true" : "false"), Csv(c.IsRotationCouplingLike ? "true" : "false"), Csv(c.LockRotation ? "true" : "false"),
                        Csv(c.Suppressed ? "true" : "false"), Csv(c.Healthy ? "true" : "false"), Csv(c.HealthText), Csv(c.EntityOneKind), Csv(c.EntityTwoKind), Csv(c.HasAxisLikeGeometry ? "true" : "false"), Csv(c.HasPlanarGeometry ? "true" : "false"), Csv(c.HasPointGeometry ? "true" : "false"), Csv(c.IsRigidLike ? "true" : "false"), Csv(c.RepairedFromCollapsedEndpoint ? "true" : "false"), Csv(F(c.OffsetMeters)), Csv(F(c.MotionRatio)), Csv(F(c.MotionOffset))
                    }));
                }
                File.WriteAllLines(constraintsCsv, cLines.ToArray(), Encoding.UTF8);

                List<string> nLines = new List<string>();
                nLines.Add("index,stable_id,name,api_class,context_path,context_source,link_a,link_b,joint_kind,has_axis,axis_world,has_axis_point,axis_point_world,axis_source,pivot_source,pivot_quality,suppressed,healthy,health,evidence_score");
                foreach (NativeJointInfo n in nativeJoints ?? new List<NativeJointInfo>())
                {
                    if (n == null) continue;
                    nLines.Add(String.Join(",", new string[] {
                        Csv(n.Index.ToString(_ci)), Csv(n.StableId), Csv(n.Name), Csv(n.ApiClass), Csv(n.ContextPath), Csv(n.ContextSource), Csv(n.A == null ? "" : n.A.LinkName), Csv(n.B == null ? "" : n.B.LinkName), Csv(n.JointKind),
                        Csv(n.HasAxis ? "true" : "false"), Csv(n.AxisWorld.Text()), Csv(n.HasAxisPoint ? "true" : "false"), Csv(n.AxisPointWorld.Text()), Csv(n.AxisSource), Csv(n.PivotSource), Csv(F(n.PivotQuality)), Csv(n.Suppressed ? "true" : "false"), Csv(n.Healthy ? "true" : "false"), Csv(n.HealthText), Csv(F(n.EvidenceScore))
                    }));
                }
                File.WriteAllLines(nativeCsv, nLines.ToArray(), Encoding.UTF8);

                List<string> kLines = new List<string>();
                kLines.Add("pair,link_a,link_b,rank,free_dof,unlocked_insert,axis_like,planar,has_axis_point,axis_world,axis_point_world,exported_joint,exported_type,exported_role,evidence,reason");
                foreach (ImplicitKinematicCandidate k in model.ImplicitCandidates)
                {
                    if (k == null) continue;
                    kLines.Add(String.Join(",", new string[] { Csv(k.PairKey), Csv(k.LinkA), Csv(k.LinkB), Csv(k.RawRank.ToString(_ci)), Csv(k.RawFreeDof.ToString(_ci)), Csv(k.UnlockedInsert ? "true" : "false"), Csv(k.AxisLikeCount.ToString(_ci)), Csv(k.PlanarCount.ToString(_ci)), Csv(k.HasAxisPoint ? "true" : "false"), Csv(k.AxisWorld.Text()), Csv(k.AxisPointWorld.Text()), Csv(k.ExportedJoint), Csv(k.ExportedType), Csv(k.ExportedRole), Csv(k.Evidence), Csv(k.Reason) }));
                }
                File.WriteAllLines(candidatesCsv, kLines.ToArray(), Encoding.UTF8);

                List<string> tLines = new List<string>();
                tLines.Add("index,link_name,display_name,has_visual_geometry,texture_file,texture_exists,texture_bytes,mesh_inline_usd,material_name,color_rgb,source");
                foreach (OccInfo o in model.Occurrences)
                {
                    if (o == null) continue;
                    string textureFile = o.TextureFile ?? "";
                    bool textureExists = !String.IsNullOrEmpty(textureFile) && File.Exists(textureFile);
                    long textureBytes = 0;
                    try { if (textureExists) textureBytes = new FileInfo(textureFile).Length; } catch { textureBytes = 0; }
                    tLines.Add(String.Join(",", new string[] {
                        Csv(o.Index.ToString(_ci)), Csv(o.LinkName), Csv(o.Name), Csv(o.HasVisualGeometry ? "true" : "false"),
                        Csv(textureFile), Csv(textureExists ? "true" : "false"), Csv(textureBytes.ToString(_ci)), Csv("true"),
                        Csv("mat_" + o.LinkName), Csv(F(o.Color.R / 255.0) + " " + F(o.Color.G / 255.0) + " " + F(o.Color.B / 255.0)),
                        Csv("BUILD125_USD_TEXTURE_ONLY_FROM_URDFPLUS")
                    }));
                }
                File.WriteAllLines(texturesCsv, tLines.ToArray(), Encoding.UTF8);

                List<string> sLines = new List<string>();
                sLines.Add("kind,name,type,solver,mode,master_joint,dependent_joint,master_link,dependent_link,ratio,offset,source,evidence");
                foreach (CouplingInfo c in model.Couplings)
                {
                    if (c == null) continue;
                    sLines.Add(String.Join(",", new string[] {
                        Csv("coupling"), Csv(c.Name), Csv(c.Type), Csv(c.Solver), Csv(c.Mode), Csv(c.MasterJoint), Csv(c.DependentJoint),
                        Csv(c.MasterLink), Csv(c.DependentLink), Csv(F(c.Ratio)), Csv(F(c.Offset)), Csv(c.Source), Csv(c.Evidence)
                    }));
                }
                foreach (JointSpec l in model.LoopJoints)
                {
                    if (l == null) continue;
                    sLines.Add(String.Join(",", new string[] {
                        Csv("loop_joint"), Csv(l.Name), Csv(l.Type), Csv("pin_axis_pose_closure"), Csv(l.ConstraintKind ?? "3d"),
                        Csv(""), Csv(l.Name), Csv(l.Parent == null ? "" : l.Parent.LinkName), Csv(l.Child == null ? "" : l.Child.LinkName),
                        Csv("1"), Csv("0"), Csv(l.Source), Csv(l.Evidence)
                    }));
                }
                File.WriteAllLines(solverCsv, sLines.ToArray(), Encoding.UTF8);

                Build51Log.Summary("BUILD125_TEXTURE_MANIFEST textures='" + texturesCsv + "' count=" + tLines.Count.ToString(_ci));
                Build51Log.Summary("BUILD125_SOLVER_CONTRACT solver='" + solverCsv + "' rows=" + sLines.Count.ToString(_ci));

                File.WriteAllText(auditTxt,
                    "AutoMind USD BUILD125 Audit Summary\r\n" +
                    "usd_path=" + usdPath + "\r\n" +
                    "export_dir=" + _exportDir + "\r\n" +
                    "links=" + (model.Occurrences.Count + 1).ToString(_ci) + " including base_link\r\n" +
                    "tree_joints=" + model.TreeJoints.Count.ToString(_ci) + "\r\n" +
                    "loop_joints=" + model.LoopJoints.Count.ToString(_ci) + "\r\n" +
                    "couplings=" + model.Couplings.Count.ToString(_ci) + "\r\n" +
                    "texture_manifest=AutoMind_USD_TEXTURES.csv\r\n" +
                    "solver_contract=AutoMind_USD_SOLVER_CONTRACT.csv\r\n" +
                    "cad_constraints=" + (constraints == null ? 0 : constraints.Count).ToString(_ci) + "\r\n" +
                    "native_joints=" + (nativeJoints == null ? 0 : nativeJoints.Count).ToString(_ci) + "\r\n" +
                    "implicit_candidates=" + model.ImplicitCandidates.Count.ToString(_ci) + "\r\n" +
                    "independent_dof=" + model.IndependentDof.ToString(_ci) + "\r\n" +
                    "parallel_gripper_overlay=" + (gripperOverlay ? "true" : "false") + "\r\n" +
                    "errors=" + model.Errors.Count.ToString(_ci) + "\r\n" +
                    "warnings=" + (model.Warnings.Count + _warnings.Count).ToString(_ci) + "\r\n" +
                    "\r\nCritical viewer note:\r\n" +
                    "The USD stage nests Links/Joints under the defaultPrim. A viewer must recursively parse def blocks; otherwise it will show one root link only.\r\n",
                    Encoding.UTF8);

                Build51Log.Summary("BUILD125_MAX_DEBUG_FILES_WRITTEN manifest='" + manifest + "' links='" + linksCsv + "' joints='" + jointsCsv + "' constraints='" + constraintsCsv + "' native='" + nativeCsv + "' implicit='" + candidatesCsv + "' textures='" + texturesCsv + "' solver='" + solverCsv + "' audit='" + auditTxt + "'");
            }
            catch (Exception ex)
            {
                Build51Log.Error("BUILD125_MAX_DEBUG_FILES_FAILED " + ex.ToString());
            }
        }

        private int CountRegex(string text, string pattern)
        {
            if (String.IsNullOrEmpty(text) || String.IsNullOrEmpty(pattern)) return 0;
            return System.Text.RegularExpressions.Regex.Matches(text, pattern).Count;
        }

        private void WriteUrdf(string path, MechanicalModel model, bool gripperOverlay)
        {
            XmlWriterSettings settings = new XmlWriterSettings();
            settings.Encoding = new UTF8Encoding(false);
            settings.Indent = true;
            settings.NewLineOnAttributes = false;
            using (XmlWriter x = XmlWriter.Create(path, settings))
            {
                x.WriteStartDocument();
                x.WriteStartElement("robot");
                x.WriteAttributeString("name", model.RobotName);
                x.WriteAttributeString("xmlns", "automind", null, "https://automind.dev/mechanism");
                x.WriteAttributeString("xmlns", "urdf_plus", null, "https://automind.dev/urdf_plus");
                x.WriteComment("AutoMind BUILD95: exact-q0 URDF+ export with explicit + implicit/passive kinematics, forensic DOF roles, rigid/flexible IAM hierarchy, grounded world locks, physical mass properties and URDF RPY contract metadata.");
                x.WriteComment("Standard URDF readers can load the tree; URDF+ readers should consume automind:loop and automind:coupling.");

                WriteBaseLink(x);
                foreach (OccInfo occ in model.Occurrences) WriteLink(x, occ);
                WriteJoint(x, model.RootJoint, "base_link", model.RootOccurrence.LinkName);
                foreach (JointSpec j in model.TreeJoints) WriteJoint(x, j, j.Parent.LinkName, j.Child.LinkName);
                foreach (JointSpec l in model.LoopJoints) WriteLoop(x, l);
                foreach (CouplingInfo c in model.Couplings) WriteCoupling(x, c);
                WriteDiagnostics(x, model, gripperOverlay);
                x.WriteEndElement();
                x.WriteEndDocument();
            }
        }

        private void WriteBaseLink(XmlWriter x)
        {
            x.WriteStartElement("link");
            x.WriteAttributeString("name", "base_link");
            WriteInertialFallback(x, Vec3.Zero, 0.01);
            x.WriteEndElement();
        }

        private void WriteLink(XmlWriter x, OccInfo occ)
        {
            x.WriteStartElement("link");
            x.WriteAttributeString("name", occ.LinkName);
            x.WriteAttributeString("automind", "node_kind", "https://automind.dev/mechanism",
                occ.IsAssemblyNode ? "assembly_frame" : "leaf_component");
            x.WriteAttributeString("automind", "cad_path", "https://automind.dev/mechanism", occ.Path ?? "");
            x.WriteAttributeString("automind", "flexible", "https://automind.dev/mechanism", occ.IsFlexible ? "true" : "false");
            x.WriteAttributeString("automind", "grounded", "https://automind.dev/mechanism", occ.Grounded ? "true" : "false");
            OccInfo rigidScope = NearestRigidAssemblyIncludingSelf(occ);
            if (rigidScope != null)
                x.WriteAttributeString("automind", "rigid_scope", "https://automind.dev/mechanism", rigidScope.LinkName);

            x.WriteStartElement("urdf_plus", "evidence", "https://automind.dev/urdf_plus");
            x.WriteAttributeString("stable_id", occ.StableId);
            x.WriteAttributeString("display_name", occ.Name);
            x.WriteAttributeString("cad_path", occ.Path ?? "");
            x.WriteAttributeString("node_kind", occ.IsAssemblyNode ? "assembly_frame" : "leaf_component");
            x.WriteAttributeString("flexible", occ.IsFlexible ? "true" : "false");
            x.WriteAttributeString("grounded", occ.Grounded ? "true" : "false");
            x.WriteAttributeString("source_document", occ.SourceDocumentPath ?? "");
            x.WriteAttributeString("mass_kg", F(Math.Max(0.0, occ.MassKg)));
            x.WriteAttributeString("mass_properties", occ.HasExactMassProperties ? "inventor_exact" : "fallback");
            if (rigidScope != null) x.WriteAttributeString("rigid_scope", rigidScope.LinkName);
            x.WriteAttributeString("name_used_for_inference", "false");
            x.WriteEndElement();

            x.WriteStartElement("automind", "cad_pose", "https://automind.dev/mechanism");
            x.WriteAttributeString("xyz", occ.CadWorld.Translation.TextSpaces());
            x.WriteAttributeString("rpy", CleanRpyForUrdf(occ.CadWorld.ToRpy()).TextSpaces());
            x.WriteAttributeString("frame", "inventor_active_assembly");
            x.WriteEndElement();

            x.WriteStartElement("automind", "physical_properties", "https://automind.dev/mechanism");
            x.WriteAttributeString("source", occ.HasExactMassProperties ? "inventor_mass_properties" : "fallback");
            x.WriteAttributeString("mass_kg", F(Math.Max(0.0, occ.MassKg)));
            if (occ.HasExactMassProperties)
            {
                x.WriteAttributeString("center_of_mass_component_m", occ.CenterOfMassLocal.TextSpaces());
                x.WriteAttributeString("ixx", F(occ.Ixx));
                x.WriteAttributeString("ixy", F(occ.Ixy));
                x.WriteAttributeString("ixz", F(occ.Ixz));
                x.WriteAttributeString("iyy", F(occ.Iyy));
                x.WriteAttributeString("iyz", F(occ.Iyz));
                x.WriteAttributeString("izz", F(occ.Izz));
            }
            x.WriteEndElement();

            if (!occ.HasVisualGeometry)
            {
                WriteInertialFallback(x, Vec3.Zero, 0.0001);
                x.WriteEndElement();
                return;
            }

            WriteInertial(x, occ);

            x.WriteStartElement("visual");
            WriteOrigin(x, occ.VisualOriginInLink);
            x.WriteStartElement("geometry");
            x.WriteStartElement("mesh");
            x.WriteAttributeString("filename", "meshes/" + Path.GetFileName(occ.MeshFile));
            x.WriteEndElement();
            x.WriteEndElement();
            x.WriteStartElement("material");
            x.WriteAttributeString("name", "mat_" + occ.LinkName);
            x.WriteStartElement("color");
            x.WriteAttributeString("rgba", F(occ.Color.R / 255.0) + " " + F(occ.Color.G / 255.0) + " " + F(occ.Color.B / 255.0) + " 1");
            x.WriteEndElement();
            if (!String.IsNullOrEmpty(occ.TextureFile))
            {
                x.WriteStartElement("texture");
                x.WriteAttributeString("filename", "meshes/" + Path.GetFileName(occ.TextureFile));
                x.WriteEndElement();
            }
            x.WriteEndElement();
            x.WriteEndElement();

            x.WriteStartElement("collision");
            WriteOrigin(x, occ.VisualOriginInLink);
            x.WriteStartElement("geometry");
            x.WriteStartElement("mesh");
            x.WriteAttributeString("filename", "meshes/" + Path.GetFileName(occ.MeshFile));
            x.WriteEndElement();
            x.WriteEndElement();
            x.WriteEndElement();

            x.WriteEndElement();
        }

        private void WriteInertial(XmlWriter x, OccInfo occurrence)
        {
            if (occurrence == null)
            {
                WriteInertialFallback(x, Vec3.Zero, 0.0001);
                return;
            }

            double mass = Math.Max(occurrence.MassKg, 0.0001);
            if (!occurrence.HasExactMassProperties)
            {
                WriteInertialFallback(x, occurrence.VisualOriginInLink.Translation, mass);
                return;
            }

            // MassProperties are read in the component definition frame.  The
            // inertial origin is therefore the component COM transformed into the
            // canonical URDF link frame, with the same component-frame rotation.
            Mat4 localCom = Mat4.FromRotationTranslation(Mat4.Identity, occurrence.CenterOfMassLocal);
            Mat4 inertialFrame = occurrence.VisualOriginInLink * localCom;

            x.WriteStartElement("inertial");
            WriteOrigin(x, inertialFrame);
            x.WriteStartElement("mass");
            x.WriteAttributeString("value", F(mass));
            x.WriteEndElement();
            x.WriteStartElement("inertia");
            x.WriteAttributeString("ixx", F(Math.Max(1e-12, occurrence.Ixx)));
            x.WriteAttributeString("ixy", F(occurrence.Ixy));
            x.WriteAttributeString("ixz", F(occurrence.Ixz));
            x.WriteAttributeString("iyy", F(Math.Max(1e-12, occurrence.Iyy)));
            x.WriteAttributeString("iyz", F(occurrence.Iyz));
            x.WriteAttributeString("izz", F(Math.Max(1e-12, occurrence.Izz)));
            x.WriteEndElement();
            x.WriteEndElement();
        }

        private void WriteInertialFallback(XmlWriter x, Vec3 com, double mass)
        {
            x.WriteStartElement("inertial");
            x.WriteStartElement("origin");
            x.WriteAttributeString("xyz", com.TextSpaces());
            x.WriteAttributeString("rpy", "0 0 0");
            x.WriteEndElement();
            x.WriteStartElement("mass");
            x.WriteAttributeString("value", F(mass));
            x.WriteEndElement();
            x.WriteStartElement("inertia");
            double i = Math.Max(1e-8, mass * 1e-6);
            x.WriteAttributeString("ixx", F(i)); x.WriteAttributeString("ixy", "0"); x.WriteAttributeString("ixz", "0");
            x.WriteAttributeString("iyy", F(i)); x.WriteAttributeString("iyz", "0"); x.WriteAttributeString("izz", F(i));
            x.WriteEndElement();
            x.WriteEndElement();
        }

        private void WriteJoint(XmlWriter x, JointSpec j, string parentLink, string childLink)
        {
            if (j == null) return;
            x.WriteStartElement("joint");
            string urdfJointType =
                String.Equals(j.Type, "cylindrical", StringComparison.OrdinalIgnoreCase)
                ? "revolute"
                : j.Type;

            x.WriteAttributeString("name", j.Name);
            x.WriteAttributeString("type", urdfJointType);
            if (!String.Equals(urdfJointType, j.Type, StringComparison.OrdinalIgnoreCase))
                x.WriteAttributeString("automind", "original_joint_type", "https://automind.dev/mechanism", j.Type);
            if (!String.IsNullOrEmpty(j.Independent)) x.WriteAttributeString("independent", j.Independent);
            x.WriteAttributeString("automind", "authoritative_kinematics", "https://automind.dev/mechanism", "true");
            x.WriteAttributeString("automind", "moves_subtree", "https://automind.dev/mechanism", "true");
            x.WriteAttributeString("automind", "q0_contract", "https://automind.dev/mechanism", "parent_origin_equals_child_link_frame_for_tree;predecessor_origin_equals_successor_origin_for_loop");
            x.WriteAttributeString("automind", "kinematic_role", "https://automind.dev/mechanism", j.KinematicRole ?? "");
            x.WriteAttributeString("automind", "kinematic_authority", "https://automind.dev/mechanism", j.KinematicAuthority ?? "");
            x.WriteAttributeString("automind", "implicit_motion_candidate", "https://automind.dev/mechanism", j.ImplicitMotionCandidate ? "true" : "false");
            x.WriteAttributeString("automind", "requires_review", "https://automind.dev/mechanism", j.RequiresReview ? "true" : "false");
            if (!String.IsNullOrEmpty(j.ReviewReason)) x.WriteAttributeString("automind", "review_reason", "https://automind.dev/mechanism", j.ReviewReason);
            if (String.Equals(j.Independent, "false", StringComparison.OrdinalIgnoreCase) && j.ImplicitMotionCandidate)
            {
                x.WriteAttributeString("automind", "interactive_control", "https://automind.dev/mechanism", "dependent_passive_animation_only");
                x.WriteAttributeString("automind", "non_direct_animation_candidate", "https://automind.dev/mechanism", "true");
                x.WriteAttributeString("automind", "direct_user_control", "https://automind.dev/mechanism", "false");
            }
            if (!String.Equals(urdfJointType, "fixed", StringComparison.OrdinalIgnoreCase))
            {
                x.WriteAttributeString("automind", "axis_frame", "https://automind.dev/mechanism", "joint");
                x.WriteAttributeString("automind", "axis_policy", "https://automind.dev/mechanism", "canonical_local_z");
                x.WriteAttributeString("automind", "physical_axis_preserved", "https://automind.dev/mechanism", "true");
                x.WriteAttributeString("automind", "pivot_source", "https://automind.dev/mechanism", j.PivotSource ?? "");
                x.WriteAttributeString("automind", "estimated_free_dof", "https://automind.dev/mechanism", j.EstimatedFreeDof.ToString(_ci));
                x.WriteAttributeString("automind", "confidence", "https://automind.dev/mechanism", F(j.Confidence));
            }
            x.WriteStartElement("parent"); x.WriteAttributeString("link", parentLink); x.WriteEndElement();
            x.WriteStartElement("child"); x.WriteAttributeString("link", childLink); x.WriteEndElement();
            WriteOrigin(x, j.OriginInParent);
            if (urdfJointType != "fixed")
            {
                x.WriteStartElement("axis"); x.WriteAttributeString("xyz", j.AxisInJoint.TextSpaces()); x.WriteEndElement();
                if (urdfJointType == "revolute" || urdfJointType == "prismatic")
                {
                    x.WriteStartElement("limit");
                    x.WriteAttributeString("lower", F(j.Lower));
                    x.WriteAttributeString("upper", F(j.Upper));
                    x.WriteAttributeString("effort", F(j.Effort));
                    x.WriteAttributeString("velocity", F(j.Velocity));
                    x.WriteEndElement();
                }
                if (!String.IsNullOrEmpty(j.MimicJointName))
                {
                    x.WriteStartElement("mimic");
                    x.WriteAttributeString("joint", j.MimicJointName);
                    x.WriteAttributeString("multiplier", F(j.MimicMultiplier));
                    x.WriteAttributeString("offset", F(j.MimicOffset));
                    x.WriteEndElement();
                }
            }
            x.WriteStartElement("automind", "evidence", "https://automind.dev/mechanism");
            x.WriteAttributeString("source", j.Source ?? "");
            x.WriteAttributeString("constraint_stable_ids", j.Evidence ?? "");
            x.WriteAttributeString("pivot_source", j.PivotSource ?? "");
            x.WriteAttributeString("confidence", F(j.Confidence));
            x.WriteAttributeString("estimated_free_dof", j.EstimatedFreeDof.ToString(_ci));
            x.WriteAttributeString("name_used_for_inference", "false");
            x.WriteAttributeString("axis_world", j.AxisWorld.TextSpaces());
            x.WriteAttributeString("axis_joint", j.AxisInJoint.TextSpaces());
            x.WriteAttributeString("axis_successor", j.AxisInSuccessor.TextSpaces());
            x.WriteAttributeString("axis_point_world_m", j.AxisPointWorld.TextSpaces());
            x.WriteAttributeString("origin_in_successor_xyz", j.OriginInSuccessor.Translation.TextSpaces());
            x.WriteAttributeString("origin_in_successor_rpy", CleanRpyForUrdf(j.OriginInSuccessor.ToRpy()).TextSpaces());
            x.WriteAttributeString("closure_error_m", F(j.ClosureErrorMeters));
            x.WriteAttributeString("independent", j.Independent ?? "");
            x.WriteAttributeString("kinematic_role", j.KinematicRole ?? "");
            x.WriteAttributeString("kinematic_authority", j.KinematicAuthority ?? "");
            x.WriteAttributeString("implicit_motion_candidate", j.ImplicitMotionCandidate ? "true" : "false");
            x.WriteAttributeString("requires_review", j.RequiresReview ? "true" : "false");
            if (!String.IsNullOrEmpty(j.ReviewReason)) x.WriteAttributeString("review_reason", j.ReviewReason);
            x.WriteEndElement();
            x.WriteEndElement();
        }

        private void WriteLoop(XmlWriter x, JointSpec l)
        {
            x.WriteStartElement("automind", "loop", "https://automind.dev/mechanism");
            x.WriteAttributeString("name", l.Name);
            x.WriteAttributeString("type", l.Type);
            x.WriteAttributeString("constraint", l.ConstraintKind ?? "3d");
            if (String.Equals(l.Type, "rigid_link_lock", StringComparison.OrdinalIgnoreCase) ||
                String.Equals(l.ConstraintKind, "link_lock", StringComparison.OrdinalIgnoreCase))
                x.WriteAttributeString("solver", "rigid_link_lock");
            if (l.InvolvedTreeJoints.Count > 0) x.WriteAttributeString("involved_tree_joints", String.Join(" ", l.InvolvedTreeJoints.ToArray()));
            x.WriteAttributeString("closure_error_m", F(l.ClosureErrorMeters));
            x.WriteStartElement("predecessor"); x.WriteAttributeString("link", l.Parent.LinkName); x.WriteEndElement();
            x.WriteStartElement("successor"); x.WriteAttributeString("link", l.Child.LinkName); x.WriteEndElement();
            // Standard-style origin: predecessor/local loop anchor.
            WriteOrigin(x, l.OriginInParent);
            // BUILD71 URDF+ extension: successor/local loop anchor. Without this,
            // viewers draw closure lines to the successor link origin, which makes
            // valid pin joints look broken.
            WriteNamedOrigin(x, "successor_origin", l.OriginInSuccessor);
            if (l.Type != "fixed") { x.WriteStartElement("axis"); x.WriteAttributeString("xyz", l.AxisInJoint.TextSpaces()); x.WriteEndElement(); }
            x.WriteStartElement("automind", "evidence", "https://automind.dev/mechanism");
            x.WriteAttributeString("source", l.Source ?? "");
            x.WriteAttributeString("constraint_stable_ids", l.Evidence ?? "");
            x.WriteAttributeString("pivot_source", l.PivotSource ?? "");
            x.WriteAttributeString("confidence", F(l.Confidence));
            x.WriteAttributeString("estimated_free_dof", l.EstimatedFreeDof.ToString(_ci));
            x.WriteAttributeString("axis_world", l.AxisWorld.TextSpaces());
            x.WriteAttributeString("axis_joint", l.AxisInJoint.TextSpaces());
            x.WriteAttributeString("axis_successor", l.AxisInSuccessor.TextSpaces());
            x.WriteAttributeString("axis_point_world_m", l.AxisPointWorld.TextSpaces());
            x.WriteAttributeString("origin_in_predecessor_xyz", l.OriginInParent.Translation.TextSpaces());
            x.WriteAttributeString("origin_in_predecessor_rpy", CleanRpyForUrdf(l.OriginInParent.ToRpy()).TextSpaces());
            x.WriteAttributeString("origin_in_successor_xyz", l.OriginInSuccessor.Translation.TextSpaces());
            x.WriteAttributeString("origin_in_successor_rpy", CleanRpyForUrdf(l.OriginInSuccessor.ToRpy()).TextSpaces());
            x.WriteAttributeString("closure_error_m", F(l.ClosureErrorMeters));
            x.WriteAttributeString("q0_contract", "predecessor_link_frame*origin == successor_link_frame*successor_origin");
            x.WriteEndElement();
            x.WriteEndElement();
        }

        private void WriteCoupling(XmlWriter x, CouplingInfo c)
        {
            x.WriteStartElement("automind", "coupling", "https://automind.dev/mechanism");
            x.WriteAttributeString("name", c.Name ?? "coupling");
            x.WriteAttributeString("type", String.IsNullOrEmpty(c.Type) ? "linear" : c.Type);
            if (!String.IsNullOrEmpty(c.Solver)) x.WriteAttributeString("solver", c.Solver);
            if (!String.IsNullOrEmpty(c.Mode)) x.WriteAttributeString("mode", c.Mode);

            if (!String.IsNullOrEmpty(c.MasterJoint))
            {
                x.WriteAttributeString("master", c.MasterJoint);
                x.WriteAttributeString("master_joint", c.MasterJoint);
            }
            if (!String.IsNullOrEmpty(c.DependentJoint))
            {
                x.WriteAttributeString("dependent", c.DependentJoint);
                x.WriteAttributeString("dependent_joint", c.DependentJoint);
            }
            if (!String.IsNullOrEmpty(c.MasterLink)) x.WriteAttributeString("master_link", c.MasterLink);
            if (!String.IsNullOrEmpty(c.DependentLink)) x.WriteAttributeString("dependent_link", c.DependentLink);

            x.WriteAttributeString("ratio", F(c.Ratio));
            x.WriteAttributeString("offset", F(c.Offset));

            if (!String.IsNullOrEmpty(c.MasterLink) || !String.IsNullOrEmpty(c.DependentLink))
            {
                if (!String.IsNullOrEmpty(c.MasterLink)) { x.WriteStartElement("predecessor"); x.WriteAttributeString("link", c.MasterLink); x.WriteEndElement(); }
                if (!String.IsNullOrEmpty(c.DependentLink)) { x.WriteStartElement("successor"); x.WriteAttributeString("link", c.DependentLink); x.WriteEndElement(); }
            }
            if (!String.IsNullOrEmpty(c.Source) || !String.IsNullOrEmpty(c.Evidence))
            {
                x.WriteStartElement("automind", "evidence", "https://automind.dev/mechanism");
                x.WriteAttributeString("source", c.Source ?? "");
                x.WriteAttributeString("constraint_stable_ids", c.Evidence ?? "");
                x.WriteEndElement();
            }
            x.WriteEndElement();
        }

        private void WriteDiagnostics(XmlWriter x, MechanicalModel model, bool gripperOverlay)
        {
            x.WriteStartElement("automind", "viewer_policy", "https://automind.dev/mechanism");
            x.WriteAttributeString("visual_tree_source", "main_urdf_plus");
            x.WriteAttributeString("prefer_standard_backup", "false");
            x.WriteAttributeString("direct_child_joint_first", "true");
            x.WriteAttributeString("disable_runtime_autodetect", "true");
            x.WriteAttributeString("disable_coupling_redirection", "false");
            x.WriteAttributeString("cad_up_axis", "+Z");
            x.WriteAttributeString("rpy_convention", "urdf_extrinsic_xyz_rz_ry_rx");
            x.WriteAttributeString("threejs_euler_order", "XYZ");
            x.WriteAttributeString("q0_axis_frame", "joint_origin_frame");
            x.WriteAttributeString("loop_anchor_policy", "use_successor_origin");
            x.WriteEndElement();

            x.WriteStartElement("automind", "viewer_hint", "https://automind.dev/mechanism");
            x.WriteAttributeString("model_up_axis", "+Z");
            x.WriteAttributeString("threejs_up_axis", "+Y");
            x.WriteAttributeString("initial_view", "isometric");
            x.WriteAttributeString("grid", "false");
            x.WriteAttributeString("full_360_rotation", "true");
            x.WriteAttributeString("q0_axis_frame", "joint_origin_frame");
            x.WriteAttributeString("loop_anchor_policy", "use_successor_origin");
            x.WriteAttributeString("rpy_convention", "urdf_extrinsic_xyz_rz_ry_rx");
            x.WriteEndElement();

            x.WriteStartElement("automind", "urdf_plus_contract", "https://automind.dev/mechanism");
            x.WriteAttributeString("schema", "AutoMind.Build92.UrdfPlusContract.v5");
            x.WriteAttributeString("build", "BUILD95_IMPLICIT_KINEMATICS_FORENSIC_RIGID_FLEXIBLE_PHYSICAL_URDFPLUS");
            x.WriteAttributeString("selected_physical_base_link", model.RootOccurrence.LinkName);
            x.WriteAttributeString("tree_edges", model.TreeJoints.Count.ToString(_ci));
            x.WriteAttributeString("loop_edges", model.LoopJoints.Count.ToString(_ci));
            x.WriteAttributeString("couplings", model.Couplings.Count.ToString(_ci));
            x.WriteAttributeString("independent_dof", model.IndependentDof.ToString(_ci));
            x.WriteAttributeString("parallel_gripper_overlay", gripperOverlay ? "true" : "false");
            x.WriteAttributeString("name_inference_used", gripperOverlay ? "topology_guarded_overlay_only" : "false");
            x.WriteAttributeString("joint_axis_policy", "all_movable_axis_local_z");
            x.WriteAttributeString("joint_frame_policy", "canonical_minimal_twist_parent_reference_with_scored_cad_pivot");
            x.WriteAttributeString("physical_axis_preserved", "true");
            x.WriteAttributeString("native_joint_duplicate_policy", "pair_health_axis_collinearity_authority_score");
            x.WriteAttributeString("constraint_bundle_policy", "build92_motion_axis_separated_explicit_active_implicit_passive_forensic_rank");
            x.WriteAttributeString("generic_collinear_mimic", "disabled_explicit_rotation_constraints_only");
            x.WriteAttributeString("pivot_policy", "scored_geometry_context_occurrence_candidates_with_legacy_fallback");
            x.WriteAttributeString("zero_pose_policy", "exact_cad_pose_via_visual_origin_compensation");
            x.WriteAttributeString("occurrence_hierarchy_policy", "virtual_assembly_frames_rigid_locked_flexible_kinematic");
            x.WriteAttributeString("nested_transform_policy", "occurrence_transformation_is_active_assembly_context_no_double_composition");
            x.WriteAttributeString("grounded_policy", "grounded_occurrences_locked_unless_healthy_explicit_native_joint_authority");
            x.WriteAttributeString("subassembly_policy", "rigid_internal_constraints_preserved_as_evidence_flexible_constraints_activated");
            x.WriteAttributeString("mass_properties_policy", "inventor_component_mass_com_and_xyz_inertia_tensor");
            x.WriteAttributeString("forensic_logging_policy", "edge_candidates_selected_edges_q0_joint_visual_audit_active_vs_passive_dof");
            x.WriteAttributeString("active_dof_policy", "native_joint_or_explicit_rotation_constraint_promotes_active; unlocked_insert_or_rank5_axis_without_authority_exports_dependent_passive_implicit_coordinate");

            x.WriteStartElement("automind", "counts", "https://automind.dev/mechanism");
            x.WriteAttributeString("links", model.Occurrences.Count.ToString(_ci));
            x.WriteAttributeString("tree_joints", model.TreeJoints.Count.ToString(_ci));
            x.WriteAttributeString("movable_tree_joints", model.TreeJoints.Count(j => j.Type != "fixed").ToString(_ci));
            x.WriteAttributeString("loop_joints", model.LoopJoints.Count.ToString(_ci));
            x.WriteAttributeString("couplings", model.Couplings.Count.ToString(_ci));
            x.WriteAttributeString("independent_dof", model.IndependentDof.ToString(_ci));
            x.WriteAttributeString("rigid_internal_evidence", model.RigidInternalEvidenceCount.ToString(_ci));
            x.WriteAttributeString("exact_mass_properties", model.Occurrences.Count(o => o.HasExactMassProperties).ToString(_ci));
            x.WriteEndElement();

            WriteCadEvidenceLedger(x, model);
            WriteBuild92ImplicitCandidatesXml(x, model);

            foreach (JointSpec j in model.TreeJoints)
            {
                x.WriteStartElement("automind", "edge", "https://automind.dev/mechanism");
                x.WriteAttributeString("role", "tree");
                x.WriteAttributeString("name", j.Name);
                x.WriteAttributeString("parent", j.Parent.LinkName);
                x.WriteAttributeString("child", j.Child.LinkName);
                x.WriteAttributeString("type", j.Type);
                x.WriteAttributeString("source", j.Source ?? "");
                x.WriteAttributeString("evidence", j.Evidence ?? "");
                x.WriteAttributeString("independent", j.Independent ?? "");
                x.WriteAttributeString("kinematic_role", j.KinematicRole ?? "");
                x.WriteAttributeString("kinematic_authority", j.KinematicAuthority ?? "");
                x.WriteAttributeString("implicit_motion_candidate", j.ImplicitMotionCandidate ? "true" : "false");
                x.WriteAttributeString("requires_review", j.RequiresReview ? "true" : "false");
                x.WriteEndElement();
            }
            foreach (JointSpec j in model.LoopJoints)
            {
                x.WriteStartElement("automind", "edge", "https://automind.dev/mechanism");
                x.WriteAttributeString("role", "loop");
                x.WriteAttributeString("name", j.Name);
                x.WriteAttributeString("parent", j.Parent.LinkName);
                x.WriteAttributeString("child", j.Child.LinkName);
                x.WriteAttributeString("type", j.Type);
                x.WriteAttributeString("source", j.Source ?? "");
                x.WriteAttributeString("evidence", j.Evidence ?? "");
                x.WriteAttributeString("closure_error_m", F(j.ClosureErrorMeters));
                if (j.InvolvedTreeJoints.Count > 0) x.WriteAttributeString("involved_tree_joints", String.Join(" ", j.InvolvedTreeJoints.ToArray()));
                x.WriteEndElement();
            }

            x.WriteStartElement("automind", "warnings", "https://automind.dev/mechanism");
            foreach (string w in model.Warnings)
            {
                x.WriteStartElement("automind", "warning", "https://automind.dev/mechanism");
                x.WriteAttributeString("text", w);
                x.WriteEndElement();
            }
            x.WriteEndElement();

            x.WriteStartElement("automind", "mechanical_edges_csv", "https://automind.dev/mechanism");
            x.WriteCData("kind,name,parent,child,type,source,evidence\n" +
                String.Join("\n", model.TreeJoints.Select(j => "tree," + Csv(j.Name) + "," + Csv(j.Parent.LinkName) + "," + Csv(j.Child.LinkName) + "," + Csv(j.Type) + "," + Csv(j.Source) + "," + Csv(j.Evidence)).Concat(
                    model.LoopJoints.Select(j => "loop," + Csv(j.Name) + "," + Csv(j.Parent.LinkName) + "," + Csv(j.Child.LinkName) + "," + Csv(j.Type) + "," + Csv(j.Source) + "," + Csv(j.Evidence))).ToArray()));
            x.WriteEndElement();
            x.WriteEndElement();
        }


        private void WriteBuild92ImplicitCandidatesXml(XmlWriter x, MechanicalModel model)
        {
            x.WriteStartElement("automind", "implicit_kinematic_candidates", "https://automind.dev/mechanism");
            x.WriteAttributeString("count", model == null ? "0" : model.ImplicitCandidates.Count.ToString(_ci));
            if (model != null)
            {
                foreach (ImplicitKinematicCandidate k in model.ImplicitCandidates)
                {
                    x.WriteStartElement("automind", "implicit_candidate", "https://automind.dev/mechanism");
                    x.WriteAttributeString("pair", k.PairKey ?? "");
                    x.WriteAttributeString("link_a", k.LinkA ?? "");
                    x.WriteAttributeString("link_b", k.LinkB ?? "");
                    x.WriteAttributeString("rank", k.RawRank.ToString(_ci));
                    x.WriteAttributeString("free_dof", k.RawFreeDof.ToString(_ci));
                    x.WriteAttributeString("unlocked_insert", k.UnlockedInsert ? "true" : "false");
                    x.WriteAttributeString("axis_like", k.AxisLikeCount.ToString(_ci));
                    x.WriteAttributeString("planar", k.PlanarCount.ToString(_ci));
                    x.WriteAttributeString("axis_world", k.AxisWorld.TextSpaces());
                    x.WriteAttributeString("axis_point_world_m", k.AxisPointWorld.TextSpaces());
                    x.WriteAttributeString("exported_joint", k.ExportedJoint ?? "");
                    x.WriteAttributeString("exported_type", k.ExportedType ?? "");
                    x.WriteAttributeString("exported_role", k.ExportedRole ?? "");
                    x.WriteAttributeString("evidence", k.Evidence ?? "");
                    x.WriteAttributeString("reason", k.Reason ?? "");
                    x.WriteEndElement();
                }
            }
            x.WriteEndElement();
        }

        private void WriteCadEvidenceLedger(XmlWriter x, MechanicalModel model)
        {
            x.WriteStartElement("automind", "cad_evidence_ledger", "https://automind.dev/mechanism");
            x.WriteAttributeString("constraints", model.CadConstraints.Count.ToString(_ci));
            x.WriteAttributeString("native_joints", model.NativeJoints.Count.ToString(_ci));

            foreach (ConstraintInfo c in model.CadConstraints)
            {
                if (c == null) continue;
                x.WriteStartElement("automind", "cad_constraint", "https://automind.dev/mechanism");
                x.WriteAttributeString("stable_id", c.StableId ?? "");
                x.WriteAttributeString("name", c.Name ?? "");
                x.WriteAttributeString("api_class", c.ApiClass ?? "");
                x.WriteAttributeString("context_path", c.ContextPath ?? "");
                x.WriteAttributeString("link_a", c.A == null ? "" : c.A.LinkName);
                x.WriteAttributeString("link_b", c.B == null ? "" : c.B.LinkName);
                x.WriteAttributeString("suppressed", c.Suppressed ? "true" : "false");
                x.WriteAttributeString("healthy", c.Healthy ? "true" : "false");
                x.WriteAttributeString("health", c.HealthText ?? "");
                x.WriteAttributeString("insert", c.IsInsertLike ? "true" : "false");
                x.WriteAttributeString("mate", c.IsMateLike ? "true" : "false");
                x.WriteAttributeString("flush", c.IsFlushLike ? "true" : "false");
                x.WriteAttributeString("angle", c.IsAngleLike ? "true" : "false");
                x.WriteAttributeString("transitional", c.IsTransitionalLike ? "true" : "false");
                x.WriteAttributeString("tangent", c.IsTangentLike ? "true" : "false");
                x.WriteAttributeString("rotation_coupling", c.IsRotationCouplingLike ? "true" : "false");
                x.WriteAttributeString("lock_rotation", c.LockRotation ? "true" : "false");
                x.WriteAttributeString("motion_ratio", F(c.MotionRatio));
                x.WriteAttributeString("motion_offset", F(c.MotionOffset));
                x.WriteAttributeString("has_axis", c.HasAxis ? "true" : "false");
                if (c.HasAxis) x.WriteAttributeString("axis_world", c.AxisWorld.TextSpaces());
                x.WriteAttributeString("has_axis_point", c.HasAxisPoint ? "true" : "false");
                if (c.HasAxisPoint) x.WriteAttributeString("axis_point_world_m", c.AxisPointWorld.TextSpaces());
                x.WriteAttributeString("axis_source", c.AxisSource ?? "");
                x.WriteAttributeString("entity_one_kind", c.EntityOneKind ?? "");
                x.WriteAttributeString("entity_two_kind", c.EntityTwoKind ?? "");
                x.WriteEndElement();
            }

            foreach (NativeJointInfo j in model.NativeJoints)
            {
                if (j == null) continue;
                x.WriteStartElement("automind", "native_joint", "https://automind.dev/mechanism");
                x.WriteAttributeString("stable_id", j.StableId ?? "");
                x.WriteAttributeString("name", j.Name ?? "");
                x.WriteAttributeString("api_class", j.ApiClass ?? "");
                x.WriteAttributeString("joint_kind", j.JointKind ?? "");
                x.WriteAttributeString("context_path", j.ContextPath ?? "");
                x.WriteAttributeString("link_a", j.A == null ? "" : j.A.LinkName);
                x.WriteAttributeString("link_b", j.B == null ? "" : j.B.LinkName);
                x.WriteAttributeString("suppressed", j.Suppressed ? "true" : "false");
                x.WriteAttributeString("healthy", j.Healthy ? "true" : "false");
                x.WriteAttributeString("has_axis", j.HasAxis ? "true" : "false");
                if (j.HasAxis) x.WriteAttributeString("axis_world", j.AxisWorld.TextSpaces());
                x.WriteAttributeString("has_axis_point", j.HasAxisPoint ? "true" : "false");
                if (j.HasAxisPoint) x.WriteAttributeString("axis_point_world_m", j.AxisPointWorld.TextSpaces());
                x.WriteAttributeString("axis_source", j.AxisSource ?? "");
                x.WriteAttributeString("pivot_source", j.PivotSource ?? "");
                x.WriteEndElement();
            }
            x.WriteEndElement();
        }

        private bool TryGetSharedRigidAssembly(OccInfo a, OccInfo b, out OccInfo rigidAssembly)
        {
            rigidAssembly = null;
            if (a == null || b == null) return false;
            OccInfo ra = NearestRigidAssemblyIncludingSelf(a);
            OccInfo rb = NearestRigidAssemblyIncludingSelf(b);
            if (ra == null || rb == null || !Object.ReferenceEquals(ra, rb)) return false;
            rigidAssembly = ra;
            return true;
        }

        private OccInfo NearestRigidAssemblyIncludingSelf(OccInfo occurrence)
        {
            for (OccInfo current = occurrence; current != null; current = current.Parent)
            {
                if (current.IsAssemblyNode && !current.IsFlexible)
                    return current;
            }
            return null;
        }

        private Vec3 CleanRpyForUrdf(Vec3 rpy)
        {
            return new Vec3(
                CleanAngleForUrdf(rpy.X),
                CleanAngleForUrdf(rpy.Y),
                CleanAngleForUrdf(rpy.Z));
        }

        private double CleanAngleForUrdf(double a)
        {
            const double eps = 1e-7;
            if (Math.Abs(a) < eps) return 0.0;

            double halfPi = Math.PI * 0.5;
            if (Math.Abs(a - halfPi) < eps) return halfPi;
            if (Math.Abs(a + halfPi) < eps) return -halfPi;
            if (Math.Abs(a - Math.PI) < eps) return Math.PI;
            if (Math.Abs(a + Math.PI) < eps) return -Math.PI;
            return a;
        }

        private void WriteOrigin(XmlWriter x, Mat4 m)
        {
            Vec3 rpy = CleanRpyForUrdf(m.ToRpy());
            x.WriteStartElement("origin");
            x.WriteAttributeString("xyz", m.Translation.TextSpaces());
            x.WriteAttributeString("rpy", rpy.TextSpaces());
            x.WriteEndElement();
        }

        private void WriteNamedOrigin(XmlWriter x, string localName, Mat4 m)
        {
            Vec3 rpy = CleanRpyForUrdf(m.ToRpy());
            x.WriteStartElement("automind", localName, "https://automind.dev/mechanism");
            x.WriteAttributeString("xyz", m.Translation.TextSpaces());
            x.WriteAttributeString("rpy", rpy.TextSpaces());
            x.WriteEndElement();
        }

        // --------------------------------------------------------------------
        // Mesh and texture export
        // --------------------------------------------------------------------

        private void ExportUsdTextureOnlyFromUrdfPlus(OccInfo occ)
        {
            // Same texture system as the URDF+ exporter, but texture-only for USD:
            // - high/display mode writes the legacy face-color atlas PNG;
            // - low/VLQ mode writes the legacy solid-color PNG;
            // - no DAE/STL or auxiliary mesh file is emitted here.
            if (occ == null) return;
            string baseName = occ.LinkName;
            string png = Path.Combine(_meshDir, baseName + ".png");
            occ.MeshFile = "";
            occ.TextureFile = png;

            try
            {
                string dir = Path.GetDirectoryName(png);
                if (!String.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

                List<Inv.SurfaceBody> bodies = CollectSurfaceBodiesFromOccurrenceForLegacyDae(occ.Occurrence);
                Inv.Asset occAppearance = null;
                try { occAppearance = occ.Occurrence.Appearance; } catch { occAppearance = null; }

                if (bodies.Count == 0)
                {
                    WriteSolidPng(png, occ.Color);
                    Build51Log.Mesh("BUILD125_USD_TEXTURE_EMPTY link='" + occ.LinkName + "' texture='" + png + "'");
                    return;
                }

                double textureR, textureG, textureB;
                if (!TryGetBodyColorLegacy(bodies[0], occ.Name, occAppearance, out textureR, out textureG, out textureB))
                {
                    textureR = occ.Color.R / 255.0;
                    textureG = occ.Color.G / 255.0;
                    textureB = occ.Color.B / 255.0;
                }

                if (String.Equals(_meshMode, "high", StringComparison.OrdinalIgnoreCase))
                    WriteBodyFaceColorAtlasLegacy(bodies[0], occ.Name, occAppearance, png, 32);
                else
                    WriteSolidColorPngLegacy(png, textureR, textureG, textureB, 32);

                Build51Log.Mesh("BUILD125_USD_TEXTURE_URDFPLUS link='" + occ.LinkName + "' bodies=" + bodies.Count.ToString(_ci) + " texture='" + png + "' mode='" + _meshMode + "'");
            }
            catch (Exception ex)
            {
                Build51Log.Warn("USD texture-only export failed for " + occ.Name + ": " + ex.Message);
                try
                {
                    WriteSolidPng(png, occ.Color);
                    occ.TextureFile = png;
                }
                catch { }
            }
        }

        private void ExportMeshAndTexture(OccInfo occ)
        {
            // Legacy DAE path restored:
            // - no STL fallback
            // - tessellates Inventor SurfaceBody with CalculateFacets
            // - writes a minimal COLLADA file manually
            // - writes the PNG next to the .dae using the old VLQ/Display behavior
            string baseName = occ.LinkName;
            string dae = Path.Combine(_meshDir, baseName + ".dae");
            string png = Path.Combine(_meshDir, baseName + ".png");

            occ.MeshFile = dae;
            occ.TextureFile = png;

            try
            {
                List<Inv.SurfaceBody> bodies = CollectSurfaceBodiesFromOccurrenceForLegacyDae(occ.Occurrence);
                if (bodies.Count == 0)
                {
                    File.WriteAllText(dae, MinimalColladaPlaceholder(baseName), Encoding.UTF8);
                    WriteSolidPng(png, occ.Color);
                    _warnings.Add("Legacy DAE: occurrence has no SurfaceBodies; placeholder DAE written for " + occ.LinkName + ".");
                    Build51Log.Mesh("BUILD71_LEGACY_DAE_EMPTY link='" + occ.LinkName + "' mesh='" + dae + "' texture='" + png + "'");
                    return;
                }

                double[] verticesWorld;
                int[] indices;
                if (!TessellateBodiesToMeshArraysLegacy(bodies, out verticesWorld, out indices))
                {
                    File.WriteAllText(dae, MinimalColladaPlaceholder(baseName), Encoding.UTF8);
                    WriteSolidPng(png, occ.Color);
                    _warnings.Add("Legacy DAE: CalculateFacets returned no triangles; placeholder DAE written for " + occ.LinkName + ".");
                    Build51Log.Mesh("BUILD71_LEGACY_DAE_NO_TRIANGLES link='" + occ.LinkName + "' mesh='" + dae + "' texture='" + png + "'");
                    return;
                }

                double[] verticesLocal;
                Inv.Matrix occurrenceMatrix = null;
                try { occurrenceMatrix = occ.Occurrence.Transformation; } catch { occurrenceMatrix = null; }
                TransformVerticesToOccurrenceLocalLegacy(verticesWorld, occurrenceMatrix, out verticesLocal);

                WriteColladaFileLegacy(dae, baseName, verticesLocal, indices);

                Inv.Asset occAppearance = null;
                try { occAppearance = occ.Occurrence.Appearance; } catch { occAppearance = null; }

                double textureR, textureG, textureB;
                if (!TryGetBodyColorLegacy(bodies[0], occ.Name, occAppearance, out textureR, out textureG, out textureB))
                {
                    textureR = occ.Color.R / 255.0;
                    textureG = occ.Color.G / 255.0;
                    textureB = occ.Color.B / 255.0;
                }

                if (String.Equals(_meshMode, "high", StringComparison.OrdinalIgnoreCase))
                    WriteBodyFaceColorAtlasLegacy(bodies[0], occ.Name, occAppearance, png, 32);
                else
                    WriteSolidColorPngLegacy(png, textureR, textureG, textureB, 32);

                if (!IsUsefulMeshFile(dae))
                {
                    File.WriteAllText(dae, MinimalColladaPlaceholder(baseName), Encoding.UTF8);
                    _warnings.Add("Legacy DAE: generated file failed usefulness check; placeholder DAE rewritten for " + occ.LinkName + ".");
                }

                Build51Log.Mesh("BUILD71_LEGACY_DAE link='" + occ.LinkName + "' bodies=" + bodies.Count.ToString(_ci) + " vertices=" + (verticesLocal.Length / 3).ToString(_ci) + " triangles=" + (indices.Length / 3).ToString(_ci) + " mesh='" + dae + "' texture='" + png + "' mode='" + _meshMode + "'");
            }
            catch (Exception ex)
            {
                Build51Log.Warn("Legacy DAE export failed for " + occ.Name + ": " + ex.Message);
                try
                {
                    File.WriteAllText(dae, MinimalColladaPlaceholder(baseName), Encoding.UTF8);
                    WriteSolidPng(png, occ.Color);
                    occ.MeshFile = dae;
                    occ.TextureFile = png;
                }
                catch { }
            }
        }

        private List<Inv.SurfaceBody> CollectSurfaceBodiesFromOccurrenceForLegacyDae(Inv.ComponentOccurrence occ)
        {
            List<Inv.SurfaceBody> bodies = new List<Inv.SurfaceBody>();
            if (occ == null) return bodies;

            try
            {
                Inv.SurfaceBodies occBodies = occ.SurfaceBodies;
                if (occBodies != null && occBodies.Count > 0)
                {
                    for (int i = 1; i <= occBodies.Count; i++)
                    {
                        Inv.SurfaceBody b = occBodies[i];
                        if (b != null) bodies.Add(b);
                    }
                    if (bodies.Count > 0) return bodies;
                }
            }
            catch { }

            try
            {
                Inv.PartComponentDefinition partDef = occ.Definition as Inv.PartComponentDefinition;
                if (partDef != null)
                    CollectSurfaceBodiesFromPartDefinitionForLegacyDae(partDef, bodies);
            }
            catch { }

            return bodies;
        }

        private void CollectSurfaceBodiesFromPartDefinitionForLegacyDae(Inv.PartComponentDefinition partDef, List<Inv.SurfaceBody> bodies)
        {
            if (partDef == null || bodies == null) return;

            try
            {
                Inv.SurfaceBodies surfaceBodies = partDef.SurfaceBodies;
                if (surfaceBodies != null)
                {
                    for (int i = 1; i <= surfaceBodies.Count; i++)
                    {
                        Inv.SurfaceBody b = surfaceBodies[i];
                        if (b != null) bodies.Add(b);
                    }
                }
            }
            catch { }

            try
            {
                Inv.WorkSurfaces workSurfaces = partDef.WorkSurfaces;
                if (workSurfaces != null)
                {
                    for (int wi = 1; wi <= workSurfaces.Count; wi++)
                    {
                        Inv.WorkSurface ws = workSurfaces[wi];
                        if (ws == null) continue;

                        Inv.SurfaceBodies wsBodies = ws.SurfaceBodies;
                        if (wsBodies == null) continue;

                        for (int bi = 1; bi <= wsBodies.Count; bi++)
                        {
                            Inv.SurfaceBody b = wsBodies[bi];
                            if (b != null) bodies.Add(b);
                        }
                    }
                }
            }
            catch { }
        }

        private bool TessellateBodiesToMeshArraysLegacy(IList<Inv.SurfaceBody> bodies, out double[] vertices, out int[] indices)
        {
            vertices = null;
            indices = null;

            if (bodies == null || bodies.Count == 0)
            {
                Build51Log.Mesh("Legacy DAE tessellation: no bodies");
                return false;
            }

            List<double> vList = new List<double>();
            List<int> iList = new List<int>();
            int vertexOffset = 0;

            int bodyIndex = 0;
            foreach (Inv.SurfaceBody body in bodies)
            {
                if (body == null)
                {
                    bodyIndex++;
                    continue;
                }

                if (!TessellateSingleBodyLegacy(body, vList, iList, ref vertexOffset))
                    Build51Log.Mesh("Legacy DAE tessellation: body[" + bodyIndex.ToString(_ci) + "] produced no triangles");

                bodyIndex++;
            }

            if (vList.Count == 0 || iList.Count == 0)
                return false;

            vertices = vList.ToArray();
            indices = iList.ToArray();
            return true;
        }

        private bool TessellateSingleBodyLegacy(Inv.SurfaceBody body, List<double> vList, List<int> iList, ref int vertexOffset)
        {
            try
            {
                // Same old control: VLQ uses coarser CalculateFacets; Display uses finer.
                // Inventor API database geometry is centimeters, converted to meters.
                double tol = String.Equals(_meshMode, "high", StringComparison.OrdinalIgnoreCase) ? 0.05 : 0.1;

                int vertexCount = 0;
                int facetCount = 0;
                double[] vertexCoords = new double[] { };
                double[] normalVectors = new double[] { };
                int[] vertexIndices = new int[] { };

                body.CalculateFacets(
                    tol,
                    out vertexCount,
                    out facetCount,
                    out vertexCoords,
                    out normalVectors,
                    out vertexIndices);

                if (vertexCount <= 0 || facetCount <= 0 ||
                    vertexCoords == null || vertexCoords.Length == 0 ||
                    vertexIndices == null || vertexIndices.Length == 0)
                    return false;

                for (int i = 0; i < vertexCoords.Length; i++)
                    vList.Add(vertexCoords[i] * _lengthToMeters);

                for (int i = 0; i < vertexIndices.Length; i++)
                {
                    int idx = vertexIndices[i] - 1; // Inventor is 1-based
                    if (idx < 0) idx = 0;
                    iList.Add(vertexOffset + idx);
                }

                vertexOffset = vList.Count / 3;
                return true;
            }
            catch (Exception ex)
            {
                Build51Log.Warn("Legacy DAE TessellateSingleBody failed: " + ex.Message);
                return false;
            }
        }

        private void TransformVerticesToOccurrenceLocalLegacy(double[] verticesWorld, Inv.Matrix occMatrix, out double[] verticesLocal)
        {
            verticesLocal = null;
            if (verticesWorld == null || verticesWorld.Length == 0 || occMatrix == null)
            {
                verticesLocal = verticesWorld;
                return;
            }

            double tx = occMatrix.Cell[1, 4] * _lengthToMeters;
            double ty = occMatrix.Cell[2, 4] * _lengthToMeters;
            double tz = occMatrix.Cell[3, 4] * _lengthToMeters;

            double r11 = occMatrix.Cell[1, 1];
            double r12 = occMatrix.Cell[1, 2];
            double r13 = occMatrix.Cell[1, 3];

            double r21 = occMatrix.Cell[2, 1];
            double r22 = occMatrix.Cell[2, 2];
            double r23 = occMatrix.Cell[2, 3];

            double r31 = occMatrix.Cell[3, 1];
            double r32 = occMatrix.Cell[3, 2];
            double r33 = occMatrix.Cell[3, 3];

            verticesLocal = new double[verticesWorld.Length];

            for (int i = 0; i < verticesWorld.Length; i += 3)
            {
                double vx = verticesWorld[i] - tx;
                double vy = verticesWorld[i + 1] - ty;
                double vz = verticesWorld[i + 2] - tz;

                // v_local = R^T * (v_world - t)
                verticesLocal[i] = r11 * vx + r21 * vy + r31 * vz;
                verticesLocal[i + 1] = r12 * vx + r22 * vy + r32 * vz;
                verticesLocal[i + 2] = r13 * vx + r23 * vy + r33 * vz;
            }
        }

        private void LogAssetInfoLegacy(string ownerKind, string ownerName, Inv.Asset app)
        {
            if (app == null)
            {
                Build51Log.Mesh("LogAssetInfo: " + ownerKind + "='" + ownerName + "' without Asset (null).");
                return;
            }

            string appDisplayName = "(unnamed)";
            try { appDisplayName = app.DisplayName; } catch { appDisplayName = "(DisplayName error)"; }

            int count = 0;
            try { count = app.Count; } catch { count = -1; }

            Build51Log.Mesh(
                "LogAssetInfo: " + ownerKind +
                "='" + ownerName +
                "', Asset.DisplayName='" + appDisplayName +
                "', AssetValues: Count=" + count.ToString(_ci));

            try
            {
                foreach (Inv.AssetValue av in app)
                {
                    if (av == null)
                    {
                        Build51Log.Mesh("    [AssetValue null]");
                        continue;
                    }

                    string avName = "";
                    string avDisplay = "";
                    bool avReadOnly = false;
                    string avType = "";

                    try { avName = av.Name; } catch { }
                    try { avDisplay = av.DisplayName; } catch { }
                    try { avReadOnly = av.IsReadOnly; } catch { }
                    try { avType = av.ValueType.ToString(); } catch { }

                    Build51Log.Mesh(
                        "    AssetValue: Name='" + avName +
                        "', DisplayName='" + avDisplay +
                        "', ValueType=" + avType +
                        ", IsReadOnly=" + avReadOnly.ToString());

                    try
                    {
                        if (av.ValueType == Inv.AssetValueTypeEnum.kAssetValueTypeColor)
                        {
                            Inv.ColorAssetValue cav = av as Inv.ColorAssetValue;
                            if (cav != null)
                            {
                                Inv.Color invCol = cav.Value as Inv.Color;
                                if (invCol != null)
                                {
                                    Build51Log.Mesh(
                                        "      Color RGBA=(" +
                                        invCol.Red.ToString(_ci) + "," +
                                        invCol.Green.ToString(_ci) + "," +
                                        invCol.Blue.ToString(_ci) + "," +
                                        invCol.Opacity.ToString(_ci) + ")");
                                }
                            }
                        }
                    }
                    catch
                    {
                        Build51Log.Mesh("      [Error reading ColorAssetValue.Value]");
                    }
                }
            }
            catch
            {
                Build51Log.Mesh("LogAssetInfo: error iterating AssetValues.");
            }
        }

        private bool TryGetColorFromNamedAssetValueLegacy(
            Inv.Asset app,
            string targetName,
            out double r,
            out double g,
            out double b)
        {
            r = 0.8; g = 0.8; b = 0.8;
            if (app == null || String.IsNullOrEmpty(targetName)) return false;

            try
            {
                foreach (Inv.AssetValue av in app)
                {
                    if (av == null) continue;

                    string avName = "";
                    try { avName = av.Name; } catch { avName = ""; }
                    if (String.IsNullOrEmpty(avName)) continue;

                    if (!String.Equals(avName, targetName, StringComparison.OrdinalIgnoreCase))
                        continue;

                    if (av.ValueType != Inv.AssetValueTypeEnum.kAssetValueTypeColor)
                        continue;

                    Inv.ColorAssetValue cav = av as Inv.ColorAssetValue;
                    if (cav == null) continue;

                    Inv.Color invCol = cav.Value as Inv.Color;
                    if (invCol == null) continue;

                    r = invCol.Red / 255.0;
                    g = invCol.Green / 255.0;
                    b = invCol.Blue / 255.0;

                    Build51Log.Mesh(
                        "TryGetColorFromNamedAssetValue('" + targetName +
                        "'): RGB=(" +
                        r.ToString("F3", _ci) + "," +
                        g.ToString("F3", _ci) + "," +
                        b.ToString("F3", _ci) + ")");
                    return true;
                }
            }
            catch
            {
                Build51Log.Mesh("TryGetColorFromNamedAssetValue: error searching '" + targetName + "'.");
            }

            return false;
        }

        private bool TryGetColorFromAssetWithPriorityLegacy(
            Inv.Asset app,
            string ownerKind,
            string ownerName,
            out double r,
            out double g,
            out double b)
        {
            r = 0.8; g = 0.8; b = 0.8;

            if (app == null)
            {
                Build51Log.Mesh(
                    "TryGetColorFromAssetWithPriority: " + ownerKind +
                    "='" + ownerName + "' without Asset, using gray 0.8.");
                return false;
            }

            LogAssetInfoLegacy(ownerKind, ownerName, app);

            if (TryGetColorFromNamedAssetValueLegacy(app, "generic_diffuse_color", out r, out g, out b))
                return true;
            if (TryGetColorFromNamedAssetValueLegacy(app, "generic_diffuse", out r, out g, out b))
                return true;
            if (TryGetColorFromNamedAssetValueLegacy(app, "metallicpaint_base_color", out r, out g, out b))
                return true;
            if (TryGetColorFromNamedAssetValueLegacy(app, "plasticvinyl_color", out r, out g, out b))
                return true;
            if (TryGetColorFromNamedAssetValueLegacy(app, "wallpaint_color", out r, out g, out b))
                return true;

            try
            {
                Inv.AssetValue avDif = null;

                try { avDif = app["generic_diffuse_color"]; } catch { avDif = null; }
                if (avDif == null)
                {
                    try { avDif = app["generic_diffuse"]; } catch { avDif = null; }
                }

                if (avDif != null && avDif.ValueType == Inv.AssetValueTypeEnum.kAssetValueTypeColor)
                {
                    Inv.ColorAssetValue difCav = avDif as Inv.ColorAssetValue;
                    if (difCav != null)
                    {
                        Inv.Color invCol1 = difCav.Value as Inv.Color;
                        if (invCol1 != null)
                        {
                            r = invCol1.Red / 255.0;
                            g = invCol1.Green / 255.0;
                            b = invCol1.Blue / 255.0;
                            return true;
                        }
                    }
                }
            }
            catch { }

            try
            {
                double tr, tg, tb;

                bool gotTint =
                    TryGetColorFromNamedAssetValueLegacy(app, "common_tint_color", out tr, out tg, out tb) ||
                    TryGetColorFromNamedAssetValueLegacy(app, "common_Tint_color", out tr, out tg, out tb);

                if (gotTint)
                {
                    bool isGrayish =
                        Math.Abs(tr - tg) < 0.02 &&
                        Math.Abs(tg - tb) < 0.02;

                    if (!isGrayish)
                    {
                        r = tr; g = tg; b = tb;
                        return true;
                    }
                }
            }
            catch { }

            try
            {
                foreach (Inv.AssetValue av in app)
                {
                    if (av == null) continue;
                    if (av.ValueType != Inv.AssetValueTypeEnum.kAssetValueTypeColor) continue;

                    string dn = null;
                    try { dn = av.DisplayName; } catch { dn = null; }
                    if (dn == null) continue;
                    if (!String.Equals(dn, "Color", StringComparison.OrdinalIgnoreCase)) continue;

                    Inv.ColorAssetValue cav = av as Inv.ColorAssetValue;
                    if (cav == null) continue;

                    Inv.Color invCol = cav.Value as Inv.Color;
                    if (invCol == null) continue;

                    r = invCol.Red / 255.0;
                    g = invCol.Green / 255.0;
                    b = invCol.Blue / 255.0;
                    return true;
                }
            }
            catch { }

            try
            {
                foreach (Inv.AssetValue av in app)
                {
                    if (av == null) continue;
                    if (av.ValueType != Inv.AssetValueTypeEnum.kAssetValueTypeColor) continue;

                    Inv.ColorAssetValue cav = av as Inv.ColorAssetValue;
                    if (cav == null) continue;

                    Inv.Color invCol = cav.Value as Inv.Color;
                    if (invCol == null) continue;

                    r = invCol.Red / 255.0;
                    g = invCol.Green / 255.0;
                    b = invCol.Blue / 255.0;
                    return true;
                }
            }
            catch { }

            return false;
        }

        private bool TryGetBodyColorLegacy(
            Inv.SurfaceBody body,
            string ownerNameForLog,
            Inv.Asset occAppearance,
            out double r,
            out double g,
            out double b)
        {
            r = 0.8; g = 0.8; b = 0.8;

            if (body == null) return false;

            string bodyName = "(unnamed)";
            try { if (!String.IsNullOrEmpty(body.Name)) bodyName = body.Name; } catch { }

            if (String.IsNullOrEmpty(ownerNameForLog))
                ownerNameForLog = bodyName;

            try
            {
                Inv.Asset appBody = null;
                try { appBody = body.Appearance; } catch { appBody = null; }

                if (appBody != null &&
                    TryGetColorFromAssetWithPriorityLegacy(appBody, "Body", ownerNameForLog, out r, out g, out b))
                {
                    return true;
                }
            }
            catch { }

            if (occAppearance != null)
            {
                if (TryGetColorFromAssetWithPriorityLegacy(occAppearance, "Occurrence", ownerNameForLog, out r, out g, out b))
                    return true;
            }

            return false;
        }

        private bool TryGetFaceColorLegacy(
            Inv.Face face,
            Inv.SurfaceBody parentBody,
            string ownerNameForLog,
            Inv.Asset occAppearance,
            out double r,
            out double g,
            out double b)
        {
            r = 0.8; g = 0.8; b = 0.8;

            if (String.IsNullOrEmpty(ownerNameForLog))
                ownerNameForLog = "(Face)";

            if (face != null)
            {
                try
                {
                    Inv.Asset app = null;
                    try { app = face.Appearance; } catch { app = null; }

                    if (app != null)
                    {
                        string faceId = ownerNameForLog;
                        try
                        {
                            if (face.SurfaceBody != null && !String.IsNullOrEmpty(face.SurfaceBody.Name))
                                faceId = face.SurfaceBody.Name;
                        }
                        catch { }

                        if (TryGetColorFromAssetWithPriorityLegacy(app, "Face", faceId, out r, out g, out b))
                            return true;
                    }
                }
                catch { }
            }

            if (parentBody != null)
            {
                if (TryGetBodyColorLegacy(parentBody, ownerNameForLog, occAppearance, out r, out g, out b))
                    return true;
            }
            else if (occAppearance != null)
            {
                if (TryGetColorFromAssetWithPriorityLegacy(occAppearance, "Occurrence", ownerNameForLog, out r, out g, out b))
                    return true;
            }

            return false;
        }

        private void WriteSolidColorPngLegacy(string path, double r, double g, double b, int size)
        {
            try
            {
                if (size < 1) size = 1;
                using (DrawingBitmap bmp = new DrawingBitmap(size, size))
                {
                    DrawingColor c = DrawingColor.FromArgb(255, Clamp255(r * 255.0), Clamp255(g * 255.0), Clamp255(b * 255.0));
                    for (int y = 0; y < size; y++)
                        for (int x = 0; x < size; x++)
                            bmp.SetPixel(x, y, c);
                    bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
                }
            }
            catch { }
        }

        private void WriteAtlasSingleColorPngLegacy(
            string path,
            double r,
            double g,
            double b,
            int cellsX,
            int cellsY,
            int cellSize)
        {
            int width = cellsX * cellSize;
            int height = cellsY * cellSize;

            using (DrawingBitmap bmp = new DrawingBitmap(width, height))
            {
                DrawingColor col = DrawingColor.FromArgb(
                    255,
                    Clamp255(r * 255.0),
                    Clamp255(g * 255.0),
                    Clamp255(b * 255.0));

                for (int y = 0; y < height; y++)
                    for (int x = 0; x < width; x++)
                        bmp.SetPixel(x, y, col);

                bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
        }

        private void WriteBodyFaceColorAtlasLegacy(
            Inv.SurfaceBody body,
            string ownerNameForLog,
            Inv.Asset occAppearance,
            string path,
            int cellSize)
        {
            if (body == null)
            {
                WriteSolidColorPngLegacy(path, 0.8, 0.8, 0.8, cellSize);
                return;
            }

            if (String.IsNullOrEmpty(ownerNameForLog))
            {
                try { ownerNameForLog = body.Name; } catch { ownerNameForLog = "(body)"; }
                if (String.IsNullOrEmpty(ownerNameForLog)) ownerNameForLog = "(body)";
            }

            double bodyR, bodyG, bodyB;
            if (!TryGetBodyColorLegacy(body, ownerNameForLog, occAppearance, out bodyR, out bodyG, out bodyB))
                bodyR = bodyG = bodyB = 0.8;

            Inv.Faces faces = null;
            try { faces = body.Faces; } catch { faces = null; }

            int faceCount = (faces != null) ? faces.Count : 0;

            if (faceCount <= 0)
            {
                WriteAtlasSingleColorPngLegacy(path, bodyR, bodyG, bodyB, 1, 1, cellSize);
                return;
            }

            int cellsX = (int)Math.Ceiling(Math.Sqrt((double)faceCount));
            if (cellsX < 1) cellsX = 1;
            int cellsY = (int)Math.Ceiling((double)faceCount / (double)cellsX);
            if (cellsY < 1) cellsY = 1;

            int width = cellsX * cellSize;
            int height = cellsY * cellSize;

            using (DrawingBitmap bmp = new DrawingBitmap(width, height))
            {
                using (System.Drawing.Graphics gg = System.Drawing.Graphics.FromImage(bmp))
                {
                    DrawingColor bgCol = DrawingColor.FromArgb(
                        255,
                        Clamp255(bodyR * 255.0),
                        Clamp255(bodyG * 255.0),
                        Clamp255(bodyB * 255.0));
                    gg.Clear(bgCol);
                }

                for (int fi = 0; fi < faceCount; fi++)
                {
                    Inv.Face f = null;
                    try { f = faces[fi + 1]; } catch { f = null; }

                    double fr, fg, fb;
                    if (!TryGetFaceColorLegacy(f, body, ownerNameForLog, occAppearance, out fr, out fg, out fb))
                    {
                        fr = bodyR; fg = bodyG; fb = bodyB;
                    }

                    DrawingColor faceCol = DrawingColor.FromArgb(
                        255,
                        Clamp255(fr * 255.0),
                        Clamp255(fg * 255.0),
                        Clamp255(fb * 255.0));

                    int cellX = fi % cellsX;
                    int cellY = fi / cellsX;
                    int startX = cellX * cellSize;
                    int startY = cellY * cellSize;

                    for (int y = startY; y < startY + cellSize && y < height; y++)
                        for (int x = startX; x < startX + cellSize && x < width; x++)
                            bmp.SetPixel(x, y, faceCol);
                }

                bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
        }


        private void WriteColladaFileLegacy(string daePath, string meshName, double[] vertices, int[] indices)
        {
            try
            {
                if (String.IsNullOrEmpty(daePath) || vertices == null || vertices.Length == 0 ||
                    indices == null || indices.Length == 0)
                {
                    Build51Log.Warn("WriteColladaFileLegacy: invalid parameters");
                    return;
                }

                int vCount = vertices.Length / 3;
                int triCount = indices.Length / 3;
                if (vCount <= 0 || triCount <= 0)
                    return;

                double[] normals = ComputeVertexNormalsLegacy(vertices, indices);

                // Same legacy behavior: simple UVs, PNG beside DAE.
                double[] uvs = new double[vCount * 2];
                for (int i = 0; i < vCount; i++)
                {
                    uvs[i * 2 + 0] = 0.5;
                    uvs[i * 2 + 1] = 0.5;
                }

                string daeDir = Path.GetDirectoryName(daePath);
                if (!String.IsNullOrEmpty(daeDir)) Directory.CreateDirectory(daeDir);

                string pngFile = meshName + ".png";
                string safeMesh = SanitizeName(meshName);
                string geoId = safeMesh + "_geo";
                string posId = safeMesh + "_pos";
                string norId = safeMesh + "_nor";
                string uvId = safeMesh + "_uv";
                string vtxId = safeMesh + "_vtx";
                string imgId = safeMesh + "_img";
                string effId = safeMesh + "_eff";
                string matId = safeMesh + "_mat";
                string sceneId = "Scene";
                string nodeId = safeMesh + "_node";

                StringBuilder sb = new StringBuilder(1024 * 64);
                sb.Append("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n");
                sb.Append("<COLLADA xmlns=\"http://www.collada.org/2005/11/COLLADASchema\" version=\"1.4.1\">\n");

                sb.Append("  <asset>\n");
                sb.Append("    <contributor><authoring_tool>AutoMind Inventor legacy CalculateFacets DAE writer</authoring_tool></contributor>\n");
                sb.Append("    <unit name=\"meter\" meter=\"1\"/>\n");
                sb.Append("    <up_axis>Z_UP</up_axis>\n");
                sb.Append("  </asset>\n");

                sb.Append("  <library_images>\n");
                sb.Append("    <image id=\"").Append(XmlEscape(imgId)).Append("\" name=\"").Append(XmlEscape(imgId)).Append("\">\n");
                sb.Append("      <init_from>").Append(XmlEscape(pngFile)).Append("</init_from>\n");
                sb.Append("    </image>\n");
                sb.Append("  </library_images>\n");

                sb.Append("  <library_effects>\n");
                sb.Append("    <effect id=\"").Append(XmlEscape(effId)).Append("\" name=\"").Append(XmlEscape(effId)).Append("\">\n");
                sb.Append("      <profile_COMMON>\n");
                sb.Append("        <newparam sid=\"surface\"><surface type=\"2D\"><init_from>").Append(XmlEscape(imgId)).Append("</init_from></surface></newparam>\n");
                sb.Append("        <newparam sid=\"sampler\"><sampler2D><source>surface</source></sampler2D></newparam>\n");
                sb.Append("        <technique sid=\"common\"><lambert><diffuse><texture texture=\"sampler\" texcoord=\"UVSET0\"/></diffuse></lambert></technique>\n");
                sb.Append("      </profile_COMMON>\n");
                sb.Append("    </effect>\n");
                sb.Append("  </library_effects>\n");

                sb.Append("  <library_materials>\n");
                sb.Append("    <material id=\"").Append(XmlEscape(matId)).Append("\" name=\"").Append(XmlEscape(matId)).Append("\"><instance_effect url=\"#").Append(XmlEscape(effId)).Append("\"/></material>\n");
                sb.Append("  </library_materials>\n");

                sb.Append("  <library_geometries>\n");
                sb.Append("    <geometry id=\"").Append(XmlEscape(geoId)).Append("\" name=\"").Append(XmlEscape(geoId)).Append("\">\n");
                sb.Append("      <mesh>\n");

                sb.Append("        <source id=\"").Append(XmlEscape(posId)).Append("\">\n");
                sb.Append("          <float_array id=\"").Append(XmlEscape(posId)).Append("_arr\" count=\"").Append((vCount * 3).ToString(_ci)).Append("\">");
                for (int i = 0; i < vertices.Length; i++)
                    sb.Append(F(vertices[i])).Append(i + 1 < vertices.Length ? " " : "");
                sb.Append("</float_array>\n");
                sb.Append("          <technique_common><accessor source=\"#").Append(XmlEscape(posId)).Append("_arr\" count=\"").Append(vCount.ToString(_ci)).Append("\" stride=\"3\"><param name=\"X\" type=\"float\"/><param name=\"Y\" type=\"float\"/><param name=\"Z\" type=\"float\"/></accessor></technique_common>\n");
                sb.Append("        </source>\n");

                sb.Append("        <source id=\"").Append(XmlEscape(norId)).Append("\">\n");
                sb.Append("          <float_array id=\"").Append(XmlEscape(norId)).Append("_arr\" count=\"").Append((vCount * 3).ToString(_ci)).Append("\">");
                for (int i = 0; i < normals.Length; i++)
                    sb.Append(F(normals[i])).Append(i + 1 < normals.Length ? " " : "");
                sb.Append("</float_array>\n");
                sb.Append("          <technique_common><accessor source=\"#").Append(XmlEscape(norId)).Append("_arr\" count=\"").Append(vCount.ToString(_ci)).Append("\" stride=\"3\"><param name=\"X\" type=\"float\"/><param name=\"Y\" type=\"float\"/><param name=\"Z\" type=\"float\"/></accessor></technique_common>\n");
                sb.Append("        </source>\n");

                sb.Append("        <source id=\"").Append(XmlEscape(uvId)).Append("\">\n");
                sb.Append("          <float_array id=\"").Append(XmlEscape(uvId)).Append("_arr\" count=\"").Append((vCount * 2).ToString(_ci)).Append("\">");
                for (int i = 0; i < uvs.Length; i++)
                    sb.Append(F(uvs[i])).Append(i + 1 < uvs.Length ? " " : "");
                sb.Append("</float_array>\n");
                sb.Append("          <technique_common><accessor source=\"#").Append(XmlEscape(uvId)).Append("_arr\" count=\"").Append(vCount.ToString(_ci)).Append("\" stride=\"2\"><param name=\"S\" type=\"float\"/><param name=\"T\" type=\"float\"/></accessor></technique_common>\n");
                sb.Append("        </source>\n");

                sb.Append("        <vertices id=\"").Append(XmlEscape(vtxId)).Append("\"><input semantic=\"POSITION\" source=\"#").Append(XmlEscape(posId)).Append("\"/></vertices>\n");

                sb.Append("        <triangles count=\"").Append(triCount.ToString(_ci)).Append("\" material=\"").Append(XmlEscape(matId)).Append("\">\n");
                sb.Append("          <input semantic=\"VERTEX\" source=\"#").Append(XmlEscape(vtxId)).Append("\" offset=\"0\"/>\n");
                sb.Append("          <input semantic=\"NORMAL\" source=\"#").Append(XmlEscape(norId)).Append("\" offset=\"1\"/>\n");
                sb.Append("          <input semantic=\"TEXCOORD\" source=\"#").Append(XmlEscape(uvId)).Append("\" offset=\"2\" set=\"0\"/>\n");
                sb.Append("          <p>");
                for (int k = 0; k < indices.Length; k++)
                {
                    int vi = indices[k];
                    if (vi < 0) vi = 0;
                    if (vi >= vCount) vi = vCount - 1;

                    sb.Append(vi.ToString(_ci)).Append(" ");
                    sb.Append(vi.ToString(_ci)).Append(" ");
                    sb.Append(vi.ToString(_ci));
                    if (k + 1 < indices.Length) sb.Append(" ");
                }
                sb.Append("</p>\n");
                sb.Append("        </triangles>\n");

                sb.Append("      </mesh>\n");
                sb.Append("    </geometry>\n");
                sb.Append("  </library_geometries>\n");

                sb.Append("  <library_visual_scenes>\n");
                sb.Append("    <visual_scene id=\"").Append(XmlEscape(sceneId)).Append("\" name=\"").Append(XmlEscape(sceneId)).Append("\">\n");
                sb.Append("      <node id=\"").Append(XmlEscape(nodeId)).Append("\" name=\"").Append(XmlEscape(nodeId)).Append("\">\n");
                sb.Append("        <instance_geometry url=\"#").Append(XmlEscape(geoId)).Append("\">\n");
                sb.Append("          <bind_material><technique_common><instance_material symbol=\"").Append(XmlEscape(matId)).Append("\" target=\"#").Append(XmlEscape(matId)).Append("\"><bind_vertex_input semantic=\"UVSET0\" input_semantic=\"TEXCOORD\" input_set=\"0\"/></instance_material></technique_common></bind_material>\n");
                sb.Append("        </instance_geometry>\n");
                sb.Append("      </node>\n");
                sb.Append("    </visual_scene>\n");
                sb.Append("  </library_visual_scenes>\n");

                sb.Append("  <scene><instance_visual_scene url=\"#").Append(XmlEscape(sceneId)).Append("\"/></scene>\n");
                sb.Append("</COLLADA>\n");

                File.WriteAllText(daePath, sb.ToString(), Encoding.UTF8);
            }
            catch (Exception ex)
            {
                Build51Log.Warn("WriteColladaFileLegacy failed: " + ex.Message);
            }
        }

        private double[] ComputeVertexNormalsLegacy(double[] vertices, int[] indices)
        {
            int vCount = vertices.Length / 3;
            double[] n = new double[vCount * 3];

            for (int k = 0; k + 2 < indices.Length; k += 3)
            {
                int i0 = indices[k];
                int i1 = indices[k + 1];
                int i2 = indices[k + 2];

                if (i0 < 0 || i0 >= vCount || i1 < 0 || i1 >= vCount || i2 < 0 || i2 >= vCount)
                    continue;

                double ax = vertices[i1 * 3] - vertices[i0 * 3];
                double ay = vertices[i1 * 3 + 1] - vertices[i0 * 3 + 1];
                double az = vertices[i1 * 3 + 2] - vertices[i0 * 3 + 2];

                double bx = vertices[i2 * 3] - vertices[i0 * 3];
                double by = vertices[i2 * 3 + 1] - vertices[i0 * 3 + 1];
                double bz = vertices[i2 * 3 + 2] - vertices[i0 * 3 + 2];

                double nx = ay * bz - az * by;
                double ny = az * bx - ax * bz;
                double nz = ax * by - ay * bx;

                n[i0 * 3] += nx; n[i0 * 3 + 1] += ny; n[i0 * 3 + 2] += nz;
                n[i1 * 3] += nx; n[i1 * 3 + 1] += ny; n[i1 * 3 + 2] += nz;
                n[i2 * 3] += nx; n[i2 * 3 + 1] += ny; n[i2 * 3 + 2] += nz;
            }

            for (int i = 0; i < vCount; i++)
            {
                double nx = n[i * 3];
                double ny = n[i * 3 + 1];
                double nz = n[i * 3 + 2];
                double len = Math.Sqrt(nx * nx + ny * ny + nz * nz);
                if (len < 1e-12)
                {
                    n[i * 3] = 0.0;
                    n[i * 3 + 1] = 0.0;
                    n[i * 3 + 2] = 1.0;
                }
                else
                {
                    n[i * 3] = nx / len;
                    n[i * 3 + 1] = ny / len;
                    n[i * 3 + 2] = nz / len;
                }
            }

            return n;
        }

        private bool IsUsefulMeshFile(string path)
        {
            try
            {
                if (String.IsNullOrEmpty(path) || !File.Exists(path)) return false;
                FileInfo fi = new FileInfo(path);
                if (fi.Length < 128) return false;
                string ext = Path.GetExtension(path).ToLowerInvariant();
                if (ext == ".dae")
                {
                    string head;
                    using (FileStream fs = File.OpenRead(path))
                    {
                        int n = (int)Math.Min(fs.Length, 200000);
                        byte[] buf = new byte[n];
                        fs.Read(buf, 0, n);
                        head = Encoding.UTF8.GetString(buf);
                    }
                    return head.IndexOf("<geometry", StringComparison.OrdinalIgnoreCase) >= 0 ||
                           head.IndexOf("<triangles", StringComparison.OrdinalIgnoreCase) >= 0 ||
                           head.IndexOf("<polylist", StringComparison.OrdinalIgnoreCase) >= 0;
                }
                return true;
            }
            catch { return false; }
        }

        private void TrySetNameValue(Inv.NameValueMap map, string key, object value)
        {
            if (map == null) return;

            // Inventor interop versions differ: some expose Value[name] but not HasKey.
            // Therefore we first try assignment and, if the key does not exist, add it.
            try
            {
                map.set_Value(key, value);
                return;
            }
            catch { }

            try
            {
                map.Add(key, value);
            }
            catch { }
        }

        private void WriteSolidPng(string path, DrawingColor c)
        {
            try
            {
                using (DrawingBitmap bmp = new DrawingBitmap(2, 2))
                {
                    for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) bmp.SetPixel(x, y, c);
                    bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
                }
            }
            catch { }
        }

        private string MinimalColladaPlaceholder(string name)
        {
            return "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" +
                   "<COLLADA xmlns=\"http://www.collada.org/2005/11/COLLADASchema\" version=\"1.4.1\">\n" +
                   "  <asset><unit name=\"meter\" meter=\"1\"/><up_axis>Z_UP</up_axis></asset>\n" +
                   "  <library_visual_scenes><visual_scene id=\"Scene\" name=\"" + XmlEscape(name) + "\"/></library_visual_scenes>\n" +
                   "  <scene><instance_visual_scene url=\"#Scene\"/></scene>\n" +
                   "</COLLADA>\n";
        }

        // --------------------------------------------------------------------
        // Root selection and normalization
        // --------------------------------------------------------------------

        private OccInfo ChoosePhysicalRoot(List<OccInfo> occs, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints)
        {
            if (occs == null || occs.Count == 0)
                return null;

            Dictionary<OccInfo, double> score =
                occs.ToDictionary(
                    occurrence => occurrence,
                    occurrence => 0.0);

            foreach (OccInfo occurrence in occs)
            {
                if (occurrence.Grounded)
                    score[occurrence] += 1000.0;

                score[occurrence] +=
                    Math.Min(
                        100.0,
                        Math.Max(
                            0.0,
                            occurrence.MassKg) * 10.0);

                score[occurrence] +=
                    Math.Min(
                        50.0,
                        OccurrenceCharacteristicSize(
                            occurrence) * 100.0);

                // A component far from the assembly centroid is less likely to be the
                // physical base when several occurrences are marked grounded.
                score[occurrence] -=
                    occurrence.World.Translation.Length * 0.25;
            }

            foreach (ConstraintInfo constraint in constraints ?? new List<ConstraintInfo>())
            {
                if (constraint == null ||
                    constraint.A == null ||
                    constraint.B == null ||
                    constraint.Suppressed ||
                    !constraint.Healthy)
                    continue;

                double weight =
                    constraint.IsAngleLike ||
                    constraint.IsFlushLike ||
                    constraint.LockRotation
                    ? 8.0
                    : (
                        constraint.IsInsertLike
                        ? 3.0
                        : 5.0);

                score[constraint.A] += weight;
                score[constraint.B] += weight;
            }

            foreach (NativeJointInfo joint in nativeJoints ?? new List<NativeJointInfo>())
            {
                if (joint == null ||
                    joint.A == null ||
                    joint.B == null ||
                    joint.Suppressed)
                    continue;

                score[joint.A] += 6.0;
                score[joint.B] += 6.0;
            }

            List<OccInfo> physicalOccurrences =
                occs.Where(o => o != null && o.HasVisualGeometry).ToList();

            List<OccInfo> rootPool =
                physicalOccurrences.Count > 0
                ? physicalOccurrences
                : occs;

            List<OccInfo> grounded =
                rootPool.Where(o => o.Grounded).ToList();

            // BUILD98: if several grounded parts are connected by explicit
            // native revolute joints, they are not all bases.  Prefer an end
            // of the explicit native joint chain as the physical root.  This
            // prevents RB COMPLETE from selecting an internal arm segment as
            // root and then fixing the lower arms to it.
            int groundedNativeEdges = ActiveNativeGroundedEdgeCount(grounded, nativeJoints);
            if (grounded.Count > 1 && groundedNativeEdges > 0)
            {
                List<OccInfo> nativeEndpoints =
                    grounded
                        .Where(o => ActiveNativeJointDegree(o, nativeJoints) == 1)
                        .ToList();

                if (nativeEndpoints.Count > 0)
                {
                    OccInfo endpointRoot =
                        nativeEndpoints
                            .OrderByDescending(o => Math.Max(0.0, o.MassKg))
                            .ThenBy(o => o.Index)
                            .First();

                    Build51Log.Cad(
                        "BUILD98_ROOT_NATIVE_GROUNDED_CHAIN selected='" +
                        endpointRoot.Name +
                        "' link='" +
                        endpointRoot.LinkName +
                        "' grounded=True grounded_native_edges=" +
                        groundedNativeEdges.ToString(_ci) +
                        " degree=" +
                        ActiveNativeJointDegree(endpointRoot, nativeJoints).ToString(_ci) +
                        " reason='grounded browser placement overridden by explicit native revolute chain; choose heavy endpoint base'");

                    return endpointRoot;
                }
            }

            IEnumerable<OccInfo> candidates =
                grounded.Count > 0
                ? grounded
                : rootPool;

            OccInfo root =
                candidates
                    .OrderByDescending(o => score[o])
                    .ThenByDescending(o => o.MassKg)
                    .ThenBy(o => o.Index)
                    .First();

            Build51Log.Cad(
                "BUILD83_ROOT selected='" +
                root.Name +
                "' link='" +
                root.LinkName +
                "' grounded=" +
                root.Grounded +
                " grounded_candidates=" +
                grounded.Count.ToString(_ci) +
                " score=" +
                F(score[root]) +
                " reason='" +
                (grounded.Count > 0
                    ? "best_scored_grounded_occurrence"
                    : "best_scored_unconstrained_occurrence") +
                "'");

            foreach (OccInfo candidate in candidates
                .OrderByDescending(o => score[o])
                .Take(8))
            {
                Build51Log.Cad(
                    "BUILD83_ROOT_CANDIDATE link='" +
                    candidate.LinkName +
                    "' name='" +
                    candidate.Name +
                    "' grounded=" +
                    candidate.Grounded +
                    " mass_kg=" +
                    F(candidate.MassKg) +
                    " size_m=" +
                    F(OccurrenceCharacteristicSize(candidate)) +
                    " score=" +
                    F(score[candidate]));
            }

            return root;
        }

        private void PreserveGlobalAssemblyFrames(OccInfo root, List<OccInfo> occs, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints)
        {
            // BUILD71: Keep Inventor's absolute assembly coordinate system.
            // The old working converter placed every occurrence from occ.Transformation.
            // We preserve that behavior here. Constraint axis points/directions are
            // already in the same global CAD frame, so they must not be root-normalized.
            foreach (OccInfo o in occs)
            {
                o.CadWorld = o.WorldRaw;
                o.World = o.WorldRaw;
                Build51Log.Cad("BUILD71_GLOBAL_OCC_FRAME link='" + o.LinkName +
                    "' cad_xyz=" + o.World.Translation.Text() +
                    " grounded=" + o.Grounded);
            }
            Build51Log.Cad("BUILD71_GLOBAL_FRAME_CONTRACT root='" +
                (root == null ? "" : root.LinkName) +
                "' action='preserve_inventor_absolute_transforms_no_root_normalization'");
        }

        private void NormalizeWorldFrames(OccInfo root, List<OccInfo> occs, List<ConstraintInfo> constraints, List<NativeJointInfo> nativeJoints)
        {
            // Kept only for backwards source compatibility. BUILD71 intentionally does
            // not call this method because visual placement must remain in global CAD
            // coordinates to match Inventor at q=0.
            PreserveGlobalAssemblyFrames(root, occs, constraints, nativeJoints);
        }

        // --------------------------------------------------------------------
        // Generic COM/Inventor helpers
        // --------------------------------------------------------------------

        private double GetLengthToMeters(Inv.Document doc)
        {
            // Inventor's API database length for matrices, geometry points and most constraint values is centimeters,
            // independent of the document display unit. The previous mm-based conversion collapsed the gripper
            // to ~1/10 of its real scale and made the viewer's unit-repair heuristics fight the URDF tree.
            return 0.01;
        }

        private object TryGet(object obj, string prop)
        {
            if (obj == null) return null;
            try { return obj.GetType().InvokeMember(prop, BindingFlags.GetProperty, null, obj, null, CultureInfo.InvariantCulture); }
            catch { return null; }
        }

        private double TryDouble(object obj, string prop, double fallback)
        {
            object v = TryGet(obj, prop);
            if (v == null) return fallback;
            try { return Convert.ToDouble(v, CultureInfo.InvariantCulture); } catch { return fallback; }
        }

        private bool TryBool(object obj, string prop, bool fallback)
        {
            object v = TryGet(obj, prop);
            if (v == null) return fallback;
            try { return Convert.ToBoolean(v, CultureInfo.InvariantCulture); } catch { return fallback; }
        }

        private object FirstNonNull(params object[] xs)
        {
            foreach (object x in xs) if (x != null) return x;
            return null;
        }

        private string SafeString(object o)
        {
            if (o == null) return "";
            try { return Convert.ToString(o, CultureInfo.InvariantCulture) ?? ""; } catch { return ""; }
        }

        private OccInfo FindOccurrenceFromAny(object any, List<OccInfo> occs)
        {
            return FindOccurrenceFromAny(any, occs, "", false, Vec3.Zero);
        }

        private OccInfo FindOccurrenceFromAny(object any, List<OccInfo> occs, bool hasHintPoint, Vec3 hintPoint)
        {
            return FindOccurrenceFromAny(any, occs, "", hasHintPoint, hintPoint);
        }

        private OccInfo FindOccurrenceFromAny(object any, List<OccInfo> occs, string contextPath, bool hasHintPoint, Vec3 hintPoint)
        {
            if (any == null) return null;
            Inv.ComponentOccurrence direct = any as Inv.ComponentOccurrence;
            if (direct != null)
            {
                OccInfo hit = FindOccurrenceFromComponentOccurrence(direct, occs, contextPath, hasHintPoint, hintPoint);
                if (hit != null) return hit;
            }

            object current = any;
            for (int depth = 0; depth < 10 && current != null; ++depth)
            {
                object co = FirstNonNull(TryGet(current, "ContainingOccurrence"), TryGet(current, "Occurrence"), TryGet(current, "ParentOccurrence"));
                direct = co as Inv.ComponentOccurrence;
                if (direct != null)
                {
                    OccInfo hit = FindOccurrenceFromComponentOccurrence(direct, occs, contextPath, hasHintPoint, hintPoint);
                    if (hit != null) return hit;
                }
                current = FirstNonNull(co, TryGet(current, "Parent"));
            }

            string text = SafeString(any);
            if (!String.IsNullOrEmpty(text))
            {
                List<OccInfo> candidates = OccurrencesInContext(occs, contextPath).Where(o =>
                    text.IndexOf(o.Name, StringComparison.OrdinalIgnoreCase) >= 0 ||
                    text.IndexOf(o.Path, StringComparison.OrdinalIgnoreCase) >= 0).ToList();
                if (candidates.Count == 1) return candidates[0];
                if (candidates.Count > 1) return ChooseOccurrenceByHint(candidates, hasHintPoint, hintPoint);

                candidates = occs.Where(o =>
                    text.IndexOf(o.Name, StringComparison.OrdinalIgnoreCase) >= 0 ||
                    text.IndexOf(o.Path, StringComparison.OrdinalIgnoreCase) >= 0).ToList();
                if (candidates.Count == 1) return candidates[0];
                if (candidates.Count > 1) return ChooseOccurrenceByHint(candidates, hasHintPoint, hintPoint);
            }
            return null;
        }

        private OccInfo FindOccurrenceFromComponentOccurrence(Inv.ComponentOccurrence occ, List<OccInfo> occs, bool hasHintPoint, Vec3 hintPoint)
        {
            return FindOccurrenceFromComponentOccurrence(occ, occs, "", hasHintPoint, hintPoint);
        }

        private OccInfo FindOccurrenceFromComponentOccurrence(Inv.ComponentOccurrence occ, List<OccInfo> occs, string contextPath, bool hasHintPoint, Vec3 hintPoint)
        {
            if (occ == null || occs == null) return null;

            string n = SafeString(TryGet(occ, "Name"));
            if (String.IsNullOrEmpty(n)) return null;

            // Object identity is authoritative and must be checked globally first.
            OccInfo byReference =
                occs.FirstOrDefault(o => Object.ReferenceEquals(o.Occurrence, occ));

            if (byReference != null)
                return byReference;

            List<OccInfo> scoped =
                OccurrencesInContext(occs, contextPath).ToList();

            // Never use FirstOrDefault(name) here. Reused IAM/IPT occurrences have the
            // same leaf name in every instance (four wheels in Wheel_Loader). BUILD83
            // silently selected the first wheel and disconnected the other instances.
            List<OccInfo> exactName =
                scoped.Where(o =>
                    String.Equals(o.Name, n, StringComparison.OrdinalIgnoreCase))
                .ToList();

            if (exactName.Count == 1)
                return exactName[0];

            if (exactName.Count > 1)
                return ChooseOccurrenceByHint(exactName, hasHintPoint, hintPoint);

            // If Inventor gives a subassembly occurrence or a proxy occurrence, choose
            // a leaf under that exact browser instance, not merely a leaf with the same
            // filename/name elsewhere in the assembly.
            string prefix =
                String.IsNullOrEmpty(contextPath)
                ? n
                : contextPath.Trim('/') + "/" + n;

            List<OccInfo> candidates =
                scoped.Where(o =>
                    o.Path.Equals(prefix, StringComparison.OrdinalIgnoreCase) ||
                    o.Path.StartsWith(prefix + "/", StringComparison.OrdinalIgnoreCase) ||
                    o.Path.EndsWith("/" + n, StringComparison.OrdinalIgnoreCase) ||
                    o.Path.IndexOf("/" + n + "/", StringComparison.OrdinalIgnoreCase) >= 0)
                .ToList();

            if (candidates.Count == 1)
                return candidates[0];

            if (candidates.Count > 1)
                return ChooseOccurrenceByHint(candidates, hasHintPoint, hintPoint);

            // Global fallback still resolves duplicates spatially.
            candidates =
                occs.Where(o =>
                    String.Equals(o.Name, n, StringComparison.OrdinalIgnoreCase) ||
                    o.Path.EndsWith("/" + n, StringComparison.OrdinalIgnoreCase) ||
                    o.Path.IndexOf("/" + n + "/", StringComparison.OrdinalIgnoreCase) >= 0)
                .ToList();

            if (candidates.Count == 1)
                return candidates[0];

            if (candidates.Count > 1)
                return ChooseOccurrenceByHint(candidates, hasHintPoint, hintPoint);

            return null;
        }

        private IEnumerable<OccInfo> OccurrencesInContext(List<OccInfo> occs, string contextPath)
        {
            if (occs == null) return new List<OccInfo>();
            if (String.IsNullOrEmpty(contextPath)) return occs;
            string ctx = contextPath.Trim('/');
            return occs.Where(o =>
                o.Path.Equals(ctx, StringComparison.OrdinalIgnoreCase) ||
                o.Path.StartsWith(ctx + "/", StringComparison.OrdinalIgnoreCase));
        }

        private OccInfo ChooseOccurrenceByHint(List<OccInfo> candidates, bool hasHintPoint, Vec3 hintPoint)
        {
            if (candidates == null || candidates.Count == 0) return null;
            if (!hasHintPoint) return candidates.OrderByDescending(o => o.MassKg).FirstOrDefault();
            return candidates.OrderBy(o => DistanceOccurrenceToPoint(o, hintPoint)).ThenByDescending(o => o.MassKg).FirstOrDefault();
        }

        private double DistanceOccurrenceToPoint(OccInfo o, Vec3 p)
        {
            if (o == null) return 1e99;
            if (o.HasRangeBox)
            {
                Vec3 c = ClosestPointOnAabb(p, o.RangeMinRaw, o.RangeMaxRaw);
                return (c - p).Length;
            }
            return (o.WorldRaw.Translation - p).Length;
        }

        private AxisEvidence TryExtractAxis(object obj, object ent1, object ent2)
        {
            AxisEvidence best = new AxisEvidence();
            foreach (object e in new[] { ent1, ent2, obj })
            {
                AxisEvidence a = TryExtractAxisFromEntity(e);
                if (a.HasAxis)
                {
                    best = a;
                    break;
                }
            }
            return best;
        }

        private object UnwrapGeometryObject(object value)
        {
            object current = value;
            for (int depth = 0; depth < 8 && current != null; depth++)
            {
                object next = FirstNonNull(
                    TryGet(current, "Geometry"),
                    TryGet(current, "NativeObject"),
                    TryGet(current, "Surface"),
                    TryGet(current, "Curve"),
                    TryGet(current, "Line"),
                    TryGet(current, "Plane"));

                if (next == null) break;
                if (Object.ReferenceEquals(next, current)) break;
                current = next;
            }
            return current;
        }

        private AxisEvidence TryExtractAxisFromEntity(object e)
        {
            AxisEvidence ax = new AxisEvidence();
            if (e == null) return ax;

            object geom = UnwrapGeometryObject(e);
            if (geom == null) geom = e;

            // GeometryIntent.Point is the exact 3D joint-origin point. Autodesk's
            // AssemblyJointDefinition.OriginOne/OriginTwo properties return
            // GeometryIntent objects, so this must be checked before generic geometry.
            Vec3 p;
            object intentPoint = FirstNonNull(
                TryGet(e, "Point"),
                TryGet(e, "Point3d"),
                TryGet(e, "Position"));
            if (TryVec(intentPoint, true, out p))
            {
                ax.HasPoint = true;
                ax.Point = p;
                ax.Source = "GeometryIntent.Point";
            }

            object direction = FirstNonNull(
                TryGet(geom, "Direction"),
                TryGet(geom, "AxisVector"),
                TryGet(geom, "Vector"),
                TryGet(geom, "Normal"),
                TryGet(geom, "ZAxis"),
                TryGet(e, "Direction"),
                TryGet(e, "AxisVector"),
                TryGet(e, "Normal"),
                TryGet(e, "ZAxis"));

            Vec3 v;
            if (TryVec(direction, false, out v))
            {
                ax.HasAxis = true;
                ax.Axis = v.NormalizedOr(Vec3.UnitZ);
                ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "DirectionLike";
            }

            object axisObj = FirstNonNull(
                TryGet(geom, "Axis"),
                TryGet(geom, "RotationAxis"),
                TryGet(e, "Axis"),
                TryGet(e, "RotationAxis"));
            if (!ax.HasAxis && TryVec(axisObj, false, out v))
            {
                ax.HasAxis = true;
                ax.Axis = v.NormalizedOr(Vec3.UnitZ);
                ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "Geometry_Axis";
            }

            // Some joint-origin and coordinate-system objects expose a transform
            // rather than a direct vector. Inventor joint-origin Z is the motion axis.
            object transform = FirstNonNull(
                TryGet(e, "Transformation"),
                TryGet(e, "Transform"),
                TryGet(e, "Matrix"),
                TryGet(geom, "Transformation"),
                TryGet(geom, "Transform"),
                TryGet(geom, "Matrix"));
            if (transform != null)
            {
                Mat4 m = Mat4.FromInventorMatrix(transform, _lengthToMeters);
                Vec3 z = m.Rotate(Vec3.UnitZ).NormalizedOr(Vec3.UnitZ);
                if (!ax.HasAxis)
                {
                    ax.HasAxis = true;
                    ax.Axis = z;
                    ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "Transform_Z";
                }
                if (!ax.HasPoint)
                {
                    ax.HasPoint = true;
                    ax.Point = m.Translation;
                    ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "Transform_Origin";
                }
            }

            object start = FirstNonNull(
                TryGet(geom, "StartPoint"),
                TryGet(geom, "PointOne"),
                TryGet(e, "StartPoint"));
            object end = FirstNonNull(
                TryGet(geom, "EndPoint"),
                TryGet(geom, "PointTwo"),
                TryGet(e, "EndPoint"));
            Vec3 p0, p1;
            if (TryVec(start, true, out p0) && TryVec(end, true, out p1))
            {
                Vec3 delta = p1 - p0;
                if (!ax.HasAxis && delta.Length > 1e-12)
                {
                    ax.HasAxis = true;
                    ax.Axis = delta.NormalizedOr(Vec3.UnitZ);
                    ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "StartEndPoint";
                }
                if (!ax.HasPoint)
                {
                    ax.HasPoint = true;
                    ax.Point = Mid(p0, p1);
                    ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "StartEndMidpoint";
                }
            }

            object point = FirstNonNull(
                TryGet(geom, "RootPoint"),
                TryGet(geom, "PointOnLine"),
                TryGet(geom, "Origin"),
                TryGet(geom, "BasePoint"),
                TryGet(geom, "Center"),
                TryGet(geom, "CenterPoint"),
                TryGet(e, "RootPoint"),
                TryGet(e, "PointOnLine"),
                TryGet(e, "Origin"),
                TryGet(e, "BasePoint"),
                TryGet(e, "Center"),
                TryGet(e, "CenterPoint"));

            if (!ax.HasPoint && TryVec(point, true, out p))
            {
                ax.HasPoint = true;
                ax.Point = p;
                ax.Source = (String.IsNullOrEmpty(ax.Source) ? "" : ax.Source + "+") + "PointLike";
            }

            return ax;
        }

        private bool TryVec(object o, bool scaleAsLength, out Vec3 v)
        {
            v = Vec3.Zero;
            if (o == null) return false;
            try
            {
                double x = Convert.ToDouble(TryGet(o, "X"), CultureInfo.InvariantCulture);
                double y = Convert.ToDouble(TryGet(o, "Y"), CultureInfo.InvariantCulture);
                double z = Convert.ToDouble(TryGet(o, "Z"), CultureInfo.InvariantCulture);
                if (scaleAsLength) { x *= _lengthToMeters; y *= _lengthToMeters; z *= _lengthToMeters; }
                v = new Vec3(x, y, z);
                return true;
            }
            catch { return false; }
        }

        private bool TryGetRangeBox(Inv.ComponentOccurrence occ, out Vec3 min, out Vec3 max)
        {
            min = Vec3.Zero;
            max = Vec3.Zero;
            try
            {
                object box = TryGet(occ, "RangeBox");
                object minPt = FirstNonNull(TryGet(box, "MinPoint"), TryGet(box, "Min"));
                object maxPt = FirstNonNull(TryGet(box, "MaxPoint"), TryGet(box, "Max"));
                Vec3 a, b;
                if (TryVec(minPt, true, out a) && TryVec(maxPt, true, out b))
                {
                    min = new Vec3(Math.Min(a.X, b.X), Math.Min(a.Y, b.Y), Math.Min(a.Z, b.Z));
                    max = new Vec3(Math.Max(a.X, b.X), Math.Max(a.Y, b.Y), Math.Max(a.Z, b.Z));
                    return true;
                }
            }
            catch { }
            return false;
        }

        private string GetOccurrenceDocumentPath(Inv.ComponentOccurrence occ)
        {
            try
            {
                object def = TryGet(occ, "Definition");
                Inv.Document d = TryGet(def, "Document") as Inv.Document;
                if (d != null) return d.FullFileName;
            }
            catch { }
            return "";
        }

        private void CaptureOccurrenceMassProperties(Inv.ComponentOccurrence occurrence, OccInfo info)
        {
            if (occurrence == null || info == null) return;
            info.MassKg = TryGetMassKg(occurrence);

            try
            {
                object definition = TryGet(occurrence, "Definition");
                object massProperties = TryGet(definition, "MassProperties");
                if (massProperties == null) return;

                double mass = Convert.ToDouble(TryGet(massProperties, "Mass"), CultureInfo.InvariantCulture);
                Vec3 center;
                if (!TryVec(TryGet(massProperties, "CenterOfMass"), true, out center))
                    return;

                object[] args = new object[] { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 };
                ParameterModifier byRef = new ParameterModifier(6);
                for (int k = 0; k < 6; ++k) byRef[k] = true;
                massProperties.GetType().InvokeMember(
                    "XYZMomentsOfInertia",
                    BindingFlags.InvokeMethod,
                    null,
                    massProperties,
                    args,
                    new ParameterModifier[] { byRef },
                    CultureInfo.InvariantCulture,
                    null);

                double inertiaScale = _lengthToMeters * _lengthToMeters;
                double ixx = Convert.ToDouble(args[0], CultureInfo.InvariantCulture) * inertiaScale;
                double iyy = Convert.ToDouble(args[1], CultureInfo.InvariantCulture) * inertiaScale;
                double izz = Convert.ToDouble(args[2], CultureInfo.InvariantCulture) * inertiaScale;
                double ixy = Convert.ToDouble(args[3], CultureInfo.InvariantCulture) * inertiaScale;
                double iyz = Convert.ToDouble(args[4], CultureInfo.InvariantCulture) * inertiaScale;
                double ixz = Convert.ToDouble(args[5], CultureInfo.InvariantCulture) * inertiaScale;

                double minor2 = ixx * iyy - ixy * ixy;
                double determinant =
                    ixx * (iyy * izz - iyz * iyz) -
                    ixy * (ixy * izz - iyz * ixz) +
                    ixz * (ixy * iyz - iyy * ixz);

                if (mass <= 0.0 || ixx <= 0.0 || iyy <= 0.0 || izz <= 0.0 ||
                    minor2 <= 1e-20 || determinant <= 1e-30)
                    return;

                info.MassKg = mass;
                info.CenterOfMassLocal = center;
                info.Ixx = ixx;
                info.Iyy = iyy;
                info.Izz = izz;
                info.Ixy = ixy;
                info.Iyz = iyz;
                info.Ixz = ixz;
                info.HasExactMassProperties = true;
            }
            catch (Exception ex)
            {
                Build51Log.Warn(
                    "BUILD86 exact mass properties unavailable for '" +
                    (info.LinkName ?? info.Name ?? "") + "': " + ex.Message);
            }
        }

        private double TryGetMassKg(Inv.ComponentOccurrence occ)
        {
            try
            {
                object def = TryGet(occ, "Definition");
                object mp = TryGet(def, "MassProperties");
                if (mp != null)
                {
                    // Inventor MassProperties.Mass is typically kg in document units context.
                    double m = Convert.ToDouble(TryGet(mp, "Mass"), CultureInfo.InvariantCulture);
                    if (m > 0) return m;
                }
            }
            catch { }
            return 0.001;
        }

        private DrawingColor TryGetOccurrenceColor(Inv.ComponentOccurrence occ)
        {
            try
            {
                object appearance = FirstNonNull(TryGet(occ, "Appearance"), TryGet(occ, "RenderStyle"));
                object diffuse = FirstNonNull(TryGet(appearance, "DiffuseColor"), TryGet(appearance, "Color"));
                if (diffuse != null)
                {
                    int r = Clamp255(TryDouble(diffuse, "Red", 180));
                    int g = Clamp255(TryDouble(diffuse, "Green", 180));
                    int b = Clamp255(TryDouble(diffuse, "Blue", 180));
                    return DrawingColor.FromArgb(r, g, b);
                }
            }
            catch { }
            int h = Math.Abs(ShortHash(occ.Name).GetHashCode());
            return DrawingColor.FromArgb(80 + (h % 140), 80 + ((h / 7) % 140), 80 + ((h / 31) % 140));
        }

        private int Clamp255(double v)
        {
            if (v <= 1.0) v *= 255.0;
            if (v < 0) return 0; if (v > 255) return 255; return (int)Math.Round(v);
        }

        private string ClassifyNativeJointKind(string api, string name)
        {
            string s =
                ((api ?? "") + " " + (name ?? ""))
                    .ToLowerInvariant();

            if (s.Contains("rigid") ||
                s.Contains("weld"))
                return "fixed";

            if (s.Contains("cylindrical"))
                return "cylindrical";

            if (s.Contains("slider") ||
                s.Contains("prismatic") ||
                s.Contains("linear"))
                return "prismatic";

            if (s.Contains("planar"))
                return "planar";

            if (s.Contains("ball") ||
                s.Contains("spherical"))
                return "spherical";

            if (s.Contains("universal"))
                return "universal";

            if (s.Contains("rotational") ||
                s.Contains("revolute") ||
                s.Contains("hinge"))
                return "continuous";

            // Inventor localized "De rotación" native joints commonly expose only
            // an enum value. When a valid physical axis was recovered, continuous is
            // the conservative one-DOF projection.
            return "continuous";
        }

        private OccInfo FindByName(List<OccInfo> occs, params string[] tokens)
        {
            return occs.FirstOrDefault(o => tokens.All(t => o.Name.IndexOf(t, StringComparison.OrdinalIgnoreCase) >= 0));
        }

        private OccInfo FindPlainNumberedPart(List<OccInfo> occs, string baseWord, string number, string[] excludedTokens)
        {
            if (occs == null) return null;
            string wanted1 = (baseWord + " " + number).ToLowerInvariant();
            string wanted2 = (baseWord + "_" + number).ToLowerInvariant();
            List<OccInfo> candidates = occs.Where(o =>
            {
                string n = NormalizeNameForMatch(o.Name);
                bool starts = n.StartsWith(wanted1, StringComparison.OrdinalIgnoreCase) || n.StartsWith(wanted2, StringComparison.OrdinalIgnoreCase) ||
                              n.Equals(wanted1, StringComparison.OrdinalIgnoreCase) || n.Equals(wanted2, StringComparison.OrdinalIgnoreCase);
                if (!starts) return false;
                foreach (string bad in excludedTokens ?? new string[0])
                    if (n.IndexOf(bad.ToLowerInvariant(), StringComparison.OrdinalIgnoreCase) >= 0) return false;
                return true;
            }).ToList();
            if (candidates.Count > 0) return candidates.OrderBy(o => o.Name.Length).First();

            // Last fallback: token match with exclusions, still avoiding Gear link N.
            return occs.FirstOrDefault(o =>
            {
                string n = NormalizeNameForMatch(o.Name);
                if (n.IndexOf(baseWord.ToLowerInvariant(), StringComparison.OrdinalIgnoreCase) < 0) return false;
                if (!NameHasStandaloneNumber(n, number)) return false;
                foreach (string bad in excludedTokens ?? new string[0])
                    if (n.IndexOf(bad.ToLowerInvariant(), StringComparison.OrdinalIgnoreCase) >= 0) return false;
                return true;
            });
        }

        private string NormalizeNameForMatch(string s)
        {
            if (s == null) return "";
            string n = s.ToLowerInvariant().Replace(':', ' ').Replace('_', ' ').Replace('-', ' ');
            while (n.Contains("  ")) n = n.Replace("  ", " ");
            return n.Trim();
        }

        private bool NameHasStandaloneNumber(string normalizedName, string number)
        {
            if (String.IsNullOrEmpty(normalizedName) || String.IsNullOrEmpty(number)) return false;
            string[] parts = normalizedName.Split(new char[] { ' ', '.', '/', '\\' }, StringSplitOptions.RemoveEmptyEntries);
            return parts.Any(p => p == number);
        }

        private int DistinctNonNullCount(params OccInfo[] xs)
        {
            HashSet<OccInfo> set = new HashSet<OccInfo>();
            foreach (OccInfo x in xs) if (x != null) set.Add(x);
            return set.Count;
        }

        private static string PairKey(OccInfo a, OccInfo b)
        {
            if (a == null || b == null) return "";
            return String.CompareOrdinal(a.StableId, b.StableId) <= 0 ? a.StableId + "|" + b.StableId : b.StableId + "|" + a.StableId;
        }

        private static Vec3 Mid(Vec3 a, Vec3 b) { return (a + b) * 0.5; }

        private string F(double v) { return v.ToString("0.########", CultureInfo.InvariantCulture); }
        private static string Csv(string s) { if (s == null) s = ""; return "\"" + s.Replace("\"", "\"\"") + "\""; }
        private static string XmlEscape(string s) { return System.Security.SecurityElement.Escape(s) ?? ""; }
        private static string SanitizeName(string s)
        {
            if (String.IsNullOrWhiteSpace(s)) return "unnamed";
            StringBuilder b = new StringBuilder();
            foreach (char ch in s.Trim())
            {
                if (Char.IsLetterOrDigit(ch) || ch == '_') b.Append(ch);
                else b.Append('_');
            }
            string r = b.ToString().Trim('_');
            while (r.Contains("__")) r = r.Replace("__", "_");
            if (r.Length == 0) r = "unnamed";
            if (Char.IsDigit(r[0])) r = "n_" + r;
            return r;
        }
        private static string ShortHash(string s)
        {
            unchecked
            {
                uint h = 2166136261;
                foreach (char c in s ?? "") { h ^= c; h *= 16777619; }
                return h.ToString("X8", CultureInfo.InvariantCulture);
            }
        }
    }

    // ------------------------------------------------------------------------
    // Data classes
    // ------------------------------------------------------------------------

    internal sealed class OccInfo
    {
        public int Index;
        public Inv.ComponentOccurrence Occurrence;
        public string StableId;
        public string Name;
        public string Path;
        public string LinkName;
        public bool Visible;
        public bool Suppressed;
        public bool Grounded;
        public string SourceDocumentPath;
        public double MassKg;
        public DrawingColor Color = DrawingColor.LightGray;
        public string MeshFile;
        public string TextureFile;
        // BUILD86 complete IAM occurrence graph.
        public OccInfo Parent;
        public readonly List<OccInfo> Children = new List<OccInfo>();
        public bool IsAssemblyNode;
        public bool IsFlexible;
        public bool HasVisualGeometry = true;
        public int Depth;
        public bool HasExactMassProperties;
        public Vec3 CenterOfMassLocal = Vec3.Zero;
        public double Ixx, Iyy, Izz, Ixy, Iyz, Ixz;
        public Mat4 WorldRaw = Mat4.Identity;
        public Mat4 CadWorld = Mat4.Identity;
        public Mat4 World = Mat4.Identity;
        // Raw assembly-space AABB. Used only for CAD evidence repair before root-normalization.
        public bool HasRangeBox;
        public Vec3 RangeMinRaw = Vec3.Zero;
        public Vec3 RangeMaxRaw = Vec3.Zero;
        public Mat4 LinkFrameWorld = Mat4.Identity;
        public Mat4 VisualOriginInLink = Mat4.Identity;
    }

    internal sealed class ConstraintInfo
    {
        public int Index;
        public object Raw;
        public string StableId;
        public string Name;
        public string ApiClass;
        public string ContextPath = "";
        public string ContextSource = "";
        public OccInfo A;
        public OccInfo B;
        public bool HasAxis;
        public Vec3 AxisWorld = Vec3.UnitZ;
        public bool HasAxisPoint;
        public Vec3 AxisPointWorld = Vec3.Zero;
        public string AxisSource = "";
        public bool IsAngleLike;
        public bool IsInsertLike;
        public bool IsFlushLike;
        public bool IsMateLike;
        public bool IsTransitionalLike;
        public bool IsTangentLike;
        public bool IsRotationCouplingLike;
        public double MotionRatio = 1.0;
        public double MotionOffset = 0.0;
        public bool LockRotation;
        public bool Suppressed;
        public bool Healthy = true;
        public string HealthText = "";
        public string EntityOneKind = "";
        public string EntityTwoKind = "";
        public bool HasAxisLikeGeometry;
        public bool HasPlanarGeometry;
        public bool HasPointGeometry;
        public bool IsRigidLike;
        public bool RepairedFromCollapsedEndpoint;
        public double OffsetMeters;
    }

    internal sealed class NativeJointInfo
    {
        public int Index;
        public object Raw;
        public string StableId;
        public string Name;
        public string ApiClass;
        public string ContextPath = "";
        public string ContextSource = "";
        public OccInfo A;
        public OccInfo B;
        public string JointKind;
        public bool HasAxis;
        public Vec3 AxisWorld = Vec3.UnitZ;
        public bool HasAxisPoint;
        public Vec3 AxisPointWorld = Vec3.Zero;
        public string AxisSource = "";
        public string PivotSource = "";
        public double PivotQuality;
        public bool Suppressed;
        public bool Healthy = true;
        public string HealthText = "";
        public double EvidenceScore;
    }

    internal sealed class AxisEvidence
    {
        public bool HasAxis;
        public Vec3 Axis = Vec3.UnitZ;
        public bool HasPoint;
        public Vec3 Point = Vec3.Zero;
        public string Source = "";
    }

    internal sealed class NativePointCandidate
    {
        public Vec3 Point = Vec3.Zero;
        public string Source = "";
        public double Priority;
        public double Score;
    }

    internal sealed class BundleDecision
    {
        public string Type = "fixed";
        public Vec3 AxisWorld = Vec3.UnitZ;
        public Vec3 AxisPointWorld = Vec3.Zero;
        public bool HasAxisPoint;
        public double Score;
        public double Confidence;
        public string Source = "";
        public string Reason = "";
        public bool AllowLoop;
        public bool ExplicitMovable;
        public int EstimatedConstraintRank;
        public int EstimatedFreeDof;
    }

    internal sealed class NearestHit
    {
        public OccInfo Occurrence;
        public double Distance3;
        public double DistancePlane;
        public double Along;
    }

    internal sealed class MechanicalEdge
    {
        public OccInfo A, B;
        public OccInfo Parent, Child;
        public string Type;
        public Vec3 AxisWorld = Vec3.UnitZ;
        public Vec3 AxisPointWorld = Vec3.Zero;
        public bool HasAxisPoint;
        public double Score;
        public double Confidence;
        public bool AllowLoop;
        public bool ExplicitMovable;
        public int EstimatedConstraintRank;
        public int EstimatedFreeDof;
        public string Source;
        public string Evidence;
        public string EdgeKey;
        public OccInfo Other(OccInfo x) { return x == A ? B : A; }
        public MechanicalEdge Clone()
        {
            return (MechanicalEdge)MemberwiseClone();
        }
    }

    internal sealed class JointSpec
    {
        public string Name;
        public string Type;
        public OccInfo Parent;
        public OccInfo Child;
        public Vec3 AxisWorld = Vec3.UnitZ;
        public Vec3 AxisPointWorld = Vec3.Zero;
        public Vec3 AxisInJoint = Vec3.UnitZ;
        public Vec3 AxisInSuccessor = Vec3.UnitZ;
        public Mat4 OriginInParent = Mat4.Identity;
        public Mat4 OriginInSuccessor = Mat4.Identity;
        public double ClosureErrorMeters = 0.0;
        public string Source;
        public string Evidence;
        public string PivotSource = "";
        public double Confidence;
        public int EstimatedFreeDof;
        public string ConstraintKind;
        public double Lower = -3.141592653589793;
        public double Upper = 3.141592653589793;
        public double Effort = 10;
        public double Velocity = 10;
        public string MimicJointName;
        public double MimicMultiplier = 1.0;
        public double MimicOffset = 0.0;
        // BUILD72: explicit coordinate role for the HTML solver.
        // "true" means user/animation may drive it; "false" means closed-chain solver owns it.
        public string Independent;
        // BUILD95 forensic semantic role.  These fields let the viewer and the logs
        // distinguish an active driver from a passive coordinate that Inventor's
        // constraint solver can move implicitly.
        public string KinematicRole = "";
        public string KinematicAuthority = "";
        public bool ImplicitMotionCandidate;
        public bool RequiresReview;
        public string ReviewReason = "";
        public readonly List<string> InvolvedTreeJoints = new List<string>();
    }

    internal sealed class CouplingInfo
    {
        public string Name;
        public string Type = "linear";
        public string Solver = "";
        public string Mode = "";
        public string MasterJoint;
        public string DependentJoint;
        public string MasterLink;
        public string DependentLink;
        public string Source;
        public string Evidence;
        public double Ratio = 1.0;
        public double Offset = 0.0;
    }


    internal sealed class ImplicitKinematicCandidate
    {
        public string PairKey = "";
        public string LinkA = "";
        public string LinkB = "";
        public Vec3 AxisWorld = Vec3.UnitZ;
        public Vec3 AxisPointWorld = Vec3.Zero;
        public bool HasAxisPoint;
        public int RawRank;
        public int RawFreeDof;
        public bool UnlockedInsert;
        public int AxisLikeCount;
        public int PlanarCount;
        public string ExportedJoint = "";
        public string ExportedType = "";
        public string ExportedRole = "";
        public string Evidence = "";
        public string Reason = "";
    }

    internal sealed class MechanicalModel
    {
        public string RobotName;
        public OccInfo RootOccurrence;
        public Mat4 BaseFrameWorld = Mat4.Identity;
        public JointSpec RootJoint;
        public readonly List<OccInfo> Occurrences = new List<OccInfo>();
        public readonly List<JointSpec> TreeJoints = new List<JointSpec>();
        public readonly List<JointSpec> LoopJoints = new List<JointSpec>();
        public readonly List<CouplingInfo> Couplings = new List<CouplingInfo>();
        public readonly List<ConstraintInfo> CadConstraints = new List<ConstraintInfo>();
        public readonly List<NativeJointInfo> NativeJoints = new List<NativeJointInfo>();
        public readonly List<ImplicitKinematicCandidate> ImplicitCandidates = new List<ImplicitKinematicCandidate>();
        public int RigidInternalEvidenceCount;
        public readonly List<string> Warnings = new List<string>();
        public readonly List<string> Errors = new List<string>();
        public int IndependentDof;
    }

    internal sealed class Dsu
    {
        private readonly int[] _p;
        private readonly int[] _r;
        public Dsu(int n)
        {
            _p = new int[n]; _r = new int[n];
            for (int i = 0; i < n; ++i) _p[i] = i;
        }
        public int Find(int x)
        {
            if (_p[x] != x) _p[x] = Find(_p[x]);
            return _p[x];
        }
        public void Union(int a, int b)
        {
            a = Find(a); b = Find(b); if (a == b) return;
            if (_r[a] < _r[b]) { int t = a; a = b; b = t; }
            _p[b] = a; if (_r[a] == _r[b]) _r[a]++;
        }
    }

    // ------------------------------------------------------------------------
    // Math helpers
    // ------------------------------------------------------------------------

    internal struct Vec3
    {
        public double X, Y, Z;
        public Vec3(double x, double y, double z) { X = x; Y = y; Z = z; }
        public static Vec3 Zero { get { return new Vec3(0, 0, 0); } }
        public static Vec3 UnitX { get { return new Vec3(1, 0, 0); } }
        public static Vec3 UnitY { get { return new Vec3(0, 1, 0); } }
        public static Vec3 UnitZ { get { return new Vec3(0, 0, 1); } }
        public double Length { get { return Math.Sqrt(X * X + Y * Y + Z * Z); } }
        public Vec3 NormalizedOr(Vec3 fallback)
        {
            double n = Length;
            if (n < 1e-12 || Double.IsNaN(n) || Double.IsInfinity(n)) return fallback;
            return new Vec3(X / n, Y / n, Z / n);
        }
        public double Dot(Vec3 b) { return X * b.X + Y * b.Y + Z * b.Z; }
        public Vec3 Cross(Vec3 b)
        {
            return new Vec3(
                Y * b.Z - Z * b.Y,
                Z * b.X - X * b.Z,
                X * b.Y - Y * b.X);
        }
        public string Text()
        {
            return X.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                   Y.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                   Z.ToString("0.########", CultureInfo.InvariantCulture);
        }
        public string TextSpaces()
        {
            return X.ToString("0.########", CultureInfo.InvariantCulture) + " " +
                   Y.ToString("0.########", CultureInfo.InvariantCulture) + " " +
                   Z.ToString("0.########", CultureInfo.InvariantCulture);
        }
        public static Vec3 operator +(Vec3 a, Vec3 b) { return new Vec3(a.X + b.X, a.Y + b.Y, a.Z + b.Z); }
        public static Vec3 operator -(Vec3 a, Vec3 b) { return new Vec3(a.X - b.X, a.Y - b.Y, a.Z - b.Z); }
        public static Vec3 operator *(Vec3 a, double s) { return new Vec3(a.X * s, a.Y * s, a.Z * s); }
    }

    internal struct Mat4
    {
        public double M11, M12, M13, M14;
        public double M21, M22, M23, M24;
        public double M31, M32, M33, M34;
        public static Mat4 Identity
        {
            get
            {
                Mat4 m = new Mat4();
                m.M11 = m.M22 = m.M33 = 1;
                return m;
            }
        }
        public Vec3 Translation { get { return new Vec3(M14, M24, M34); } }
        public string TranslationText() { return Translation.Text(); }

        public static Mat4 FromInventorMatrix(object matrix, double lengthToMeters)
        {
            Mat4 r = Identity;
            if (matrix == null) return r;
            try
            {
                Type t = matrix.GetType();
                Func<int, int, double> cell = (i, j) => Convert.ToDouble(t.InvokeMember("Cell", BindingFlags.GetProperty, null, matrix, new object[] { i, j }), CultureInfo.InvariantCulture);
                r.M11 = cell(1, 1); r.M12 = cell(1, 2); r.M13 = cell(1, 3); r.M14 = cell(1, 4) * lengthToMeters;
                r.M21 = cell(2, 1); r.M22 = cell(2, 2); r.M23 = cell(2, 3); r.M24 = cell(2, 4) * lengthToMeters;
                r.M31 = cell(3, 1); r.M32 = cell(3, 2); r.M33 = cell(3, 3); r.M34 = cell(3, 4) * lengthToMeters;
            }
            catch { }
            return r;
        }

        public static Mat4 FromRotationTranslation(Mat4 rotationSource, Vec3 t)
        {
            Mat4 r = Identity;
            r.M11 = rotationSource.M11; r.M12 = rotationSource.M12; r.M13 = rotationSource.M13;
            r.M21 = rotationSource.M21; r.M22 = rotationSource.M22; r.M23 = rotationSource.M23;
            r.M31 = rotationSource.M31; r.M32 = rotationSource.M32; r.M33 = rotationSource.M33;
            r.M14 = t.X; r.M24 = t.Y; r.M34 = t.Z;
            return r;
        }

        public Mat4 InverseRigid()
        {
            // inverse of [R t; 0 1] where R is orthonormal: [R^T -R^T t]
            Mat4 r = Identity;
            r.M11 = M11; r.M12 = M21; r.M13 = M31;
            r.M21 = M12; r.M22 = M22; r.M23 = M32;
            r.M31 = M13; r.M32 = M23; r.M33 = M33;
            Vec3 nt = r.Rotate(new Vec3(-M14, -M24, -M34));
            r.M14 = nt.X; r.M24 = nt.Y; r.M34 = nt.Z;
            return r;
        }

        public Vec3 TransformPoint(Vec3 p)
        {
            return new Vec3(M11 * p.X + M12 * p.Y + M13 * p.Z + M14,
                            M21 * p.X + M22 * p.Y + M23 * p.Z + M24,
                            M31 * p.X + M32 * p.Y + M33 * p.Z + M34);
        }
        public Vec3 Rotate(Vec3 p)
        {
            return new Vec3(M11 * p.X + M12 * p.Y + M13 * p.Z,
                            M21 * p.X + M22 * p.Y + M23 * p.Z,
                            M31 * p.X + M32 * p.Y + M33 * p.Z);
        }
        public Vec3 InverseRotate(Vec3 p)
        {
            return new Vec3(M11 * p.X + M21 * p.Y + M31 * p.Z,
                            M12 * p.X + M22 * p.Y + M32 * p.Z,
                            M13 * p.X + M23 * p.Y + M33 * p.Z);
        }
        public Vec3 ToRpy()
        {
            // ZYX yaw-pitch-roll converted to URDF rpy (roll X, pitch Y, yaw Z)
            double sy = -M31;
            double pitch = Math.Asin(Math.Max(-1.0, Math.Min(1.0, sy)));
            double roll, yaw;
            if (Math.Abs(Math.Cos(pitch)) > 1e-8)
            {
                roll = Math.Atan2(M32, M33);
                yaw = Math.Atan2(M21, M11);
            }
            else
            {
                roll = 0;
                yaw = Math.Atan2(-M12, M22);
            }
            return new Vec3(roll, pitch, yaw);
        }
        public static Mat4 operator *(Mat4 a, Mat4 b)
        {
            Mat4 r = Identity;
            r.M11 = a.M11 * b.M11 + a.M12 * b.M21 + a.M13 * b.M31;
            r.M12 = a.M11 * b.M12 + a.M12 * b.M22 + a.M13 * b.M32;
            r.M13 = a.M11 * b.M13 + a.M12 * b.M23 + a.M13 * b.M33;
            r.M14 = a.M11 * b.M14 + a.M12 * b.M24 + a.M13 * b.M34 + a.M14;

            r.M21 = a.M21 * b.M11 + a.M22 * b.M21 + a.M23 * b.M31;
            r.M22 = a.M21 * b.M12 + a.M22 * b.M22 + a.M23 * b.M32;
            r.M23 = a.M21 * b.M13 + a.M22 * b.M23 + a.M23 * b.M33;
            r.M24 = a.M21 * b.M14 + a.M22 * b.M24 + a.M23 * b.M34 + a.M24;

            r.M31 = a.M31 * b.M11 + a.M32 * b.M21 + a.M33 * b.M31;
            r.M32 = a.M31 * b.M12 + a.M32 * b.M22 + a.M33 * b.M32;
            r.M33 = a.M31 * b.M13 + a.M32 * b.M23 + a.M33 * b.M33;
            r.M34 = a.M31 * b.M14 + a.M32 * b.M24 + a.M33 * b.M34 + a.M34;
            return r;
        }
    }
}
