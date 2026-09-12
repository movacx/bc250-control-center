const manifest = {"name":"BC250 Quick Access"};
const API_VERSION = 2;
const internalAPIConnection = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
if (!internalAPIConnection) {
    throw new Error('[@decky/api]: Failed to connect to the loader as as the loader API was not initialized. This is likely a bug in Decky Loader.');
}
let api;
try {
    api = internalAPIConnection.connect(API_VERSION, manifest.name);
}
catch {
    api = internalAPIConnection.connect(1, manifest.name);
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version 1. Some features may not work.`);
}
if (api._version != API_VERSION) {
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version ${api._version}. Some features may not work.`);
}
const callable = api.callable;
const toaster = api.toaster;
const definePlugin = (fn) => {
    return (...args) => {
        return fn(...args);
    };
};

var DefaultContext = {
  color: undefined,
  size: undefined,
  className: undefined,
  style: undefined,
  attr: undefined
};
var IconContext = SP_REACT.createContext && /*#__PURE__*/SP_REACT.createContext(DefaultContext);

var _excluded = ["attr", "size", "title"];
function _objectWithoutProperties(e, t) { if (null == e) return {}; var o, r, i = _objectWithoutPropertiesLoose(e, t); if (Object.getOwnPropertySymbols) { var n = Object.getOwnPropertySymbols(e); for (r = 0; r < n.length; r++) o = n[r], -1 === t.indexOf(o) && {}.propertyIsEnumerable.call(e, o) && (i[o] = e[o]); } return i; }
function _objectWithoutPropertiesLoose(r, e) { if (null == r) return {}; var t = {}; for (var n in r) if ({}.hasOwnProperty.call(r, n)) { if (-1 !== e.indexOf(n)) continue; t[n] = r[n]; } return t; }
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function ownKeys(e, r) { var t = Object.keys(e); if (Object.getOwnPropertySymbols) { var o = Object.getOwnPropertySymbols(e); r && (o = o.filter(function (r) { return Object.getOwnPropertyDescriptor(e, r).enumerable; })), t.push.apply(t, o); } return t; }
function _objectSpread(e) { for (var r = 1; r < arguments.length; r++) { var t = null != arguments[r] ? arguments[r] : {}; r % 2 ? ownKeys(Object(t), true).forEach(function (r) { _defineProperty(e, r, t[r]); }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function (r) { Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(t, r)); }); } return e; }
function _defineProperty(e, r, t) { return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: true, configurable: true, writable: true }) : e[r] = t, e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == typeof i ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != typeof t || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r); if ("object" != typeof i) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function Tree2Element(tree) {
  return tree && tree.map((node, i) => /*#__PURE__*/SP_REACT.createElement(node.tag, _objectSpread({
    key: i
  }, node.attr), Tree2Element(node.child)));
}
function GenIcon(data) {
  return props => /*#__PURE__*/SP_REACT.createElement(IconBase, _extends({
    attr: _objectSpread({}, data.attr)
  }, props), Tree2Element(data.child));
}
function IconBase(props) {
  var elem = conf => {
    var attr = props.attr,
      size = props.size,
      title = props.title,
      svgProps = _objectWithoutProperties(props, _excluded);
    var computedSize = size || conf.size || "1em";
    var className;
    if (conf.className) className = conf.className;
    if (props.className) className = (className ? className + " " : "") + props.className;
    return /*#__PURE__*/SP_REACT.createElement("svg", _extends({
      stroke: "currentColor",
      fill: "currentColor",
      strokeWidth: "0"
    }, conf.attr, attr, svgProps, {
      className: className,
      style: _objectSpread(_objectSpread({
        color: props.color || conf.color
      }, conf.style), props.style),
      height: computedSize,
      width: computedSize,
      xmlns: "http://www.w3.org/2000/svg"
    }), title && /*#__PURE__*/SP_REACT.createElement("title", null, title), props.children);
  };
  return IconContext !== undefined ? /*#__PURE__*/SP_REACT.createElement(IconContext.Consumer, null, conf => elem(conf)) : elem(DefaultContext);
}

// THIS FILE IS AUTO GENERATED
function FaTh (props) {
  return GenIcon({"attr":{"viewBox":"0 0 512 512"},"child":[{"tag":"path","attr":{"d":"M149.333 56v80c0 13.255-10.745 24-24 24H24c-13.255 0-24-10.745-24-24V56c0-13.255 10.745-24 24-24h101.333c13.255 0 24 10.745 24 24zm181.334 240v-80c0-13.255-10.745-24-24-24H205.333c-13.255 0-24 10.745-24 24v80c0 13.255 10.745 24 24 24h101.333c13.256 0 24.001-10.745 24.001-24zm32-240v80c0 13.255 10.745 24 24 24H488c13.255 0 24-10.745 24-24V56c0-13.255-10.745-24-24-24H386.667c-13.255 0-24 10.745-24 24zm-32 80V56c0-13.255-10.745-24-24-24H205.333c-13.255 0-24 10.745-24 24v80c0 13.255 10.745 24 24 24h101.333c13.256 0 24.001-10.745 24.001-24zm-205.334 56H24c-13.255 0-24 10.745-24 24v80c0 13.255 10.745 24 24 24h101.333c13.255 0 24-10.745 24-24v-80c0-13.255-10.745-24-24-24zM0 376v80c0 13.255 10.745 24 24 24h101.333c13.255 0 24-10.745 24-24v-80c0-13.255-10.745-24-24-24H24c-13.255 0-24 10.745-24 24zm386.667-56H488c13.255 0 24-10.745 24-24v-80c0-13.255-10.745-24-24-24H386.667c-13.255 0-24 10.745-24 24v80c0 13.255 10.745 24 24 24zm0 160H488c13.255 0 24-10.745 24-24v-80c0-13.255-10.745-24-24-24H386.667c-13.255 0-24 10.745-24 24v80c0 13.255 10.745 24 24 24zM181.333 376v80c0 13.255 10.745 24 24 24h101.333c13.255 0 24-10.745 24-24v-80c0-13.255-10.745-24-24-24H205.333c-13.255 0-24 10.745-24 24z"},"child":[]}]})(props);
}function FaMicrochip (props) {
  return GenIcon({"attr":{"viewBox":"0 0 512 512"},"child":[{"tag":"path","attr":{"d":"M416 48v416c0 26.51-21.49 48-48 48H144c-26.51 0-48-21.49-48-48V48c0-26.51 21.49-48 48-48h224c26.51 0 48 21.49 48 48zm96 58v12a6 6 0 0 1-6 6h-18v6a6 6 0 0 1-6 6h-42V88h42a6 6 0 0 1 6 6v6h18a6 6 0 0 1 6 6zm0 96v12a6 6 0 0 1-6 6h-18v6a6 6 0 0 1-6 6h-42v-48h42a6 6 0 0 1 6 6v6h18a6 6 0 0 1 6 6zm0 96v12a6 6 0 0 1-6 6h-18v6a6 6 0 0 1-6 6h-42v-48h42a6 6 0 0 1 6 6v6h18a6 6 0 0 1 6 6zm0 96v12a6 6 0 0 1-6 6h-18v6a6 6 0 0 1-6 6h-42v-48h42a6 6 0 0 1 6 6v6h18a6 6 0 0 1 6 6zM30 376h42v48H30a6 6 0 0 1-6-6v-6H6a6 6 0 0 1-6-6v-12a6 6 0 0 1 6-6h18v-6a6 6 0 0 1 6-6zm0-96h42v48H30a6 6 0 0 1-6-6v-6H6a6 6 0 0 1-6-6v-12a6 6 0 0 1 6-6h18v-6a6 6 0 0 1 6-6zm0-96h42v48H30a6 6 0 0 1-6-6v-6H6a6 6 0 0 1-6-6v-12a6 6 0 0 1 6-6h18v-6a6 6 0 0 1 6-6zm0-96h42v48H30a6 6 0 0 1-6-6v-6H6a6 6 0 0 1-6-6v-12a6 6 0 0 1 6-6h18v-6a6 6 0 0 1 6-6z"},"child":[]}]})(props);
}function FaFan (props) {
  return GenIcon({"attr":{"viewBox":"0 0 512 512"},"child":[{"tag":"path","attr":{"d":"M352.57 128c-28.09 0-54.09 4.52-77.06 12.86l12.41-123.11C289 7.31 279.81-1.18 269.33.13 189.63 10.13 128 77.64 128 159.43c0 28.09 4.52 54.09 12.86 77.06L17.75 224.08C7.31 223-1.18 232.19.13 242.67c10 79.7 77.51 141.33 159.3 141.33 28.09 0 54.09-4.52 77.06-12.86l-12.41 123.11c-1.05 10.43 8.11 18.93 18.59 17.62 79.7-10 141.33-77.51 141.33-159.3 0-28.09-4.52-54.09-12.86-77.06l123.11 12.41c10.44 1.05 18.93-8.11 17.62-18.59-10-79.7-77.51-141.33-159.3-141.33zM256 288a32 32 0 1 1 32-32 32 32 0 0 1-32 32z"},"child":[]}]})(props);
}function FaExclamationTriangle (props) {
  return GenIcon({"attr":{"viewBox":"0 0 576 512"},"child":[{"tag":"path","attr":{"d":"M569.517 440.013C587.975 472.007 564.806 512 527.94 512H48.054c-36.937 0-59.999-40.055-41.577-71.987L246.423 23.985c18.467-32.009 64.72-31.951 83.154 0l239.94 416.028zM288 354c-25.405 0-46 20.595-46 46s20.595 46 46 46 46-20.595 46-46-20.595-46-46-46zm-43.673-165.346l7.418 136c.347 6.364 5.609 11.346 11.982 11.346h48.546c6.373 0 11.635-4.982 11.982-11.346l7.418-136c.375-6.874-5.098-12.654-11.982-12.654h-63.383c-6.884 0-12.356 5.78-11.981 12.654z"},"child":[]}]})(props);
}function FaClock (props) {
  return GenIcon({"attr":{"viewBox":"0 0 512 512"},"child":[{"tag":"path","attr":{"d":"M256,8C119,8,8,119,8,256S119,504,256,504,504,393,504,256,393,8,256,8Zm92.49,313h0l-20,25a16,16,0,0,1-22.49,2.5h0l-67-49.72a40,40,0,0,1-15-31.23V112a16,16,0,0,1,16-16h32a16,16,0,0,1,16,16V256l58,42.5A16,16,0,0,1,348.49,321Z"},"child":[]}]})(props);
}function FaBolt (props) {
  return GenIcon({"attr":{"viewBox":"0 0 320 512"},"child":[{"tag":"path","attr":{"d":"M296 160H180.6l42.6-129.8C227.2 15 215.7 0 200 0H56C44 0 33.8 8.9 32.2 20.8l-32 240C-1.7 275.2 9.5 288 24 288h118.7L96.6 482.5c-3.6 15.2 8 29.5 23.3 29.5 8.4 0 16.4-4.4 20.8-12l176-304c9.3-15.9-2.2-36-20.7-36z"},"child":[]}]})(props);
}

const tokens = {
    colors: {
        panel: "#171717",
        panel_alt: "#1F1F1F",
        panel_raised: "#242424",
        border: "#343434",
        border_soft: "#292929",
        text: "#F2F2F2",
        muted: "#B4B4B4",
        subtle: "#8E8E8E",
        disabled_text: "#707070",
        // Controller focus ring only, same as the desktop theme.
        focus: "#6E9FFF",
        focus_soft: "rgba(110, 159, 255, 0.18)",
        // Brand accent (selection / primary action). Mirrors DARK_COLORS.orange.
        selection: "#38291D",
        // Pending / needs-attention. Deliberately not orange — see note above.
        // selection_border is now used exclusively for the CU grid's pending
        // indicator (see index.tsx CuEditor), so it shares this value.
        amber: "#E0A83E",
        amber_soft: "#3A2E12",
        console_bg: "#0A0A0A",
        blue: "#5B8DEF",
        blue_soft: "#1D2A3D",
        purple: "#B39DFF",
        purple_soft: "#2B2440",
        orange: "#F0A45D",
        orange_soft: "#38291D",
        cyan: "#56C7D4",
        cyan_soft: "#183137",
        green: "#5CBF78",
        green_soft: "#1B3224",
        red: "#FF6B64",
        red_soft: "#3A2020"}};

var codes = [
	{
		code: "BC250-CMD-001",
		markers: [
		],
		exit_statuses: [
			31,
			47,
			48,
			127
		],
		retryable: false
	},
	{
		code: "BC250-TERMINAL-001",
		markers: [
		],
		exit_statuses: [
			126
		],
		retryable: false
	},
	{
		code: "BC250-DATA-001",
		markers: [
		],
		exit_statuses: [
			65
		],
		retryable: false
	},
	{
		code: "BC250-STORAGE-001",
		markers: [
		],
		exit_statuses: [
			73,
			74
		],
		retryable: false
	},
	{
		code: "BC250-BUSY-001",
		markers: [
		],
		exit_statuses: [
			75
		],
		retryable: false
	},
	{
		code: "BC250-WORKFLOW-001",
		markers: [
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-GENERAL-001",
		markers: [
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-SERVICE-003",
		markers: [
			"QUICK_ACCESS_GPU_SERVICE",
			"QUICK_ACCESS_GPU_CONFLICT"
		],
		exit_statuses: [
			69
		],
		retryable: false
	},
	{
		code: "BC250-CONFIG-001",
		markers: [
			"QUICK_ACCESS_GPU_CONFIG"
		],
		exit_statuses: [
			78
		],
		retryable: false
	},
	{
		code: "BC250-PERM-001",
		markers: [
			"QUICK_ACCESS_PRIVILEGE"
		],
		exit_statuses: [
			11,
			13,
			14,
			15,
			16,
			17,
			71,
			77
		],
		retryable: false
	},
	{
		code: "BC250-DBUS-001",
		markers: [
			"QUICK_ACCESS_GPU_DBUS",
			"QUICK_ACCESS_GPU_ALLOWED"
		],
		exit_statuses: [
			22
		],
		retryable: false
	},
	{
		code: "BC250-TIMEOUT-001",
		markers: [
			"QUICK_ACCESS_TIMEOUT"
		],
		exit_statuses: [
			124,
			125
		],
		retryable: false
	},
	{
		code: "BC250-CU-001",
		markers: [
			"QUICK_ACCESS_CU_TABLE",
			"QUICK_ACCESS_CU_MODE",
			"QUICK_ACCESS_CU_BACKEND",
			"QUICK_ACCESS_CU_SERVICE_REMOVE",
			"QUICK_ACCESS_CU_STATE",
			"QUICK_ACCESS_CU_VERIFY",
			"QUICK_ACCESS_CU_SERVICE_PROFILE",
			"QUICK_ACCESS_CU_SERVICE_VERIFY"
		],
		exit_statuses: [
			30,
			62,
			63
		],
		retryable: false
	},
	{
		code: "BC250-CPUTOOL-001",
		markers: [
			"CPU_PAYLOAD_REFUSED"
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-UPSTREAM-404",
		markers: [
			"returned error: 404",
			"failed to synchronize all databases",
			"failed retrieving file"
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-AUTH-002",
		markers: [
			"QUICK_ACCESS_AUTH"
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-FAN-001",
		markers: [
			"QUICK_ACCESS_FAN"
		],
		exit_statuses: [
			25,
			26,
			27,
			40,
			46
		],
		retryable: false
	},
	{
		code: "BC250-CPU-001",
		markers: [
			"QUICK_ACCESS_CPU",
			"QUICK_ACCESS_CPU_VERIFY",
			"QUICK_ACCESS_CPU_SERVICE",
			"QUICK_ACCESS_CPU_SCALE_VERIFY",
			"stress is required by bc250-detect",
			"Run automatic detection at this exact frequency",
			"Manual scale must reuse the detected thermal limit",
			"bc250-detect returned values outside the requested",
			"bc250-detect did not produce a valid configuration"
		],
		exit_statuses: [
			50,
			51,
			52,
			53,
			54,
			55,
			57,
			60,
			80,
			81,
			82,
			83,
			84,
			85,
			86,
			87,
			88,
			89,
			91,
			93,
			94
		],
		retryable: false
	},
	{
		code: "BC250-HW-001",
		markers: [
			"HARDWARE_CONTEXT",
			"QUICK_ACCESS_CONTEXT"
		],
		exit_statuses: [
			10,
			12,
			18,
			19
		],
		retryable: false
	},
	{
		code: "BC250-GPU-001",
		markers: [
			"QUICK_ACCESS_GPU_BUSY",
			"gpu_busy_percent"
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-HELPER-001",
		markers: [
			"CU_HELPER_MISSING",
			"CU_BACKEND_UNTRUSTED",
			"CPU_BACKEND_MISSING",
			"HELPER_PRIVILEGE",
			"CPU_BACKEND_UNTRUSTED",
			"QUICK_ACCESS_GPU_HELPER",
			"HELPER_UNTRUSTED"
		],
		exit_statuses: [
		],
		retryable: false
	},
	{
		code: "BC250-RANGE-001",
		markers: [
			"QUICK_ACCESS_GPU_PROFILE",
			"QUICK_ACCESS_GPU_SAFE_POINT",
			"QUICK_ACCESS_GPU_VERIFY",
			"QUICK_ACCESS_CPU_SCALE",
			"Frequency must be between",
			"VID must be between",
			"Temperature must be between",
			"QAM CPU frequency must be",
			"QAM CPU VID must be",
			"QAM CPU detection uses a fixed",
			"HELPER_RANGE"
		],
		exit_statuses: [
			20,
			21,
			23,
			24,
			34,
			35,
			37,
			38,
			39,
			41,
			42,
			43,
			44,
			45,
			56,
			92
		],
		retryable: false
	},
	{
		code: "BC250-PROTOCOL-001",
		markers: [
			"Missing action.",
			"Unknown action.",
			"expects:",
			"does not accept arguments",
			"accepts only",
			"HELPER_USAGE",
			"QUICK_ACCESS_CU_SERVICE:",
			"QUICK_ACCESS_CPU_SERVICE:"
		],
		exit_statuses: [
			2,
			3,
			28,
			29,
			32,
			33,
			36,
			49,
			70,
			90
		],
		retryable: false
	}
];
var markers_longest_first = [
	"Manual scale must reuse the detected thermal limit",
	"bc250-detect returned values outside the requested",
	"bc250-detect did not produce a valid configuration",
	"Run automatic detection at this exact frequency",
	"failed to synchronize all databases",
	"stress is required by bc250-detect",
	"QUICK_ACCESS_CU_SERVICE_PROFILE",
	"QAM CPU detection uses a fixed",
	"QUICK_ACCESS_CU_SERVICE_REMOVE",
	"QUICK_ACCESS_CU_SERVICE_VERIFY",
	"QUICK_ACCESS_CPU_SCALE_VERIFY",
	"QUICK_ACCESS_GPU_SAFE_POINT",
	"Temperature must be between",
	"QUICK_ACCESS_GPU_CONFLICT",
	"does not accept arguments",
	"QUICK_ACCESS_CPU_SERVICE:",
	"Frequency must be between",
	"QAM CPU frequency must be",
	"QUICK_ACCESS_GPU_SERVICE",
	"QUICK_ACCESS_CU_SERVICE:",
	"QUICK_ACCESS_GPU_ALLOWED",
	"QUICK_ACCESS_GPU_PROFILE",
	"QUICK_ACCESS_CPU_SERVICE",
	"QUICK_ACCESS_GPU_CONFIG",
	"QUICK_ACCESS_GPU_VERIFY",
	"QUICK_ACCESS_CU_BACKEND",
	"QUICK_ACCESS_CPU_VERIFY",
	"QUICK_ACCESS_GPU_HELPER",
	"QUICK_ACCESS_PRIVILEGE",
	"QUICK_ACCESS_CPU_SCALE",
	"QUICK_ACCESS_CU_VERIFY",
	"failed retrieving file",
	"QUICK_ACCESS_GPU_DBUS",
	"QUICK_ACCESS_CU_TABLE",
	"QUICK_ACCESS_CU_STATE",
	"QUICK_ACCESS_GPU_BUSY",
	"CPU_BACKEND_UNTRUSTED",
	"QUICK_ACCESS_TIMEOUT",
	"QUICK_ACCESS_CU_MODE",
	"QUICK_ACCESS_CONTEXT",
	"CU_BACKEND_UNTRUSTED",
	"VID must be between",
	"QAM CPU VID must be",
	"CPU_PAYLOAD_REFUSED",
	"CPU_BACKEND_MISSING",
	"returned error: 404",
	"QUICK_ACCESS_AUTH",
	"CU_HELPER_MISSING",
	"QUICK_ACCESS_FAN",
	"QUICK_ACCESS_CPU",
	"HARDWARE_CONTEXT",
	"gpu_busy_percent",
	"HELPER_PRIVILEGE",
	"HELPER_UNTRUSTED",
	"Missing action.",
	"Unknown action.",
	"accepts only",
	"HELPER_USAGE",
	"HELPER_RANGE",
	"expects:"
];
var errorCatalog = {
	codes: codes,
	markers_longest_first: markers_longest_first
};

var advanced$7 = "fortgeschritten";
var apply$7 = "Anwenden";
var applyChanges$7 = "Änderungen anwenden";
var automatic$7 = "Automatisch";
var automaticApplyWarning$7 = "bc250-detect testet die CPU unter Last, leitet die Skalierung ab und wendet nur das gefundene Ergebnis an. Überwachen Sie Temperaturen und Stabilität.";
var backingSwap$7 = "Festplattentausch";
var busyAction$7 = "Warten Sie, bis der aktuelle Vorgang abgeschlossen ist, aktualisieren Sie ihn und versuchen Sie es einmal erneut.";
var busyCause$7 = "Eine frühere Presse, ein Desktop-Workflow oder ein externes Toolkit hält die Hardware-Sperre weiterhin aufrecht.";
var busyFailed$7 = "Ein weiterer BC250-Vorgang wird noch ausgeführt.";
var channel$7 = "PWM-Kanal";
var close$7 = "Entlassen";
var compute$7 = "RECHENEINHEITEN";
var cpuApplyAuto$7 = "OC anwenden · automatische Skalierung";
var cpuApplyManual$7 = "OC anwenden · manuelle Skalierung";
var cpuApplying$7 = "Anwenden der CPU-Übertaktung";
var cpuCause$7 = "Der Detektor, die Belastungsabhängigkeit, der SMU-Helfer oder das ausgewählte Profil wurden nicht sicher abgeschlossen.";
var cpuDetectHelp$7 = "Kalibriert unter Last und wendet das exakte Ergebnis an";
var cpuDetected$7 = "Erkanntes Ergebnis";
var cpuFrequency$7 = "Zielfrequenz";
var cpuGuidance$7 = "Überprüfen Sie das validierte Profil im Desktop-Modus.";
var cpuHelperUnavailable$7 = "Der geschützte CPU-Helper ist nicht verfügbar.";
var cpuLiveClock$7 = "Live-Frequenz";
var cpuManual$7 = "Manuelle Skala";
var cpuManualHelp$7 = "Erfordert eine automatische Erkennung bei dieser Frequenz";
var cpuNeedsDetection$7 = "Führen Sie eine temporäre Erkennung durch, bevor Sie ein Profil anwenden oder speichern.";
var cpuOperationFailed$7 = "Der CPU-Vorgang ist fehlgeschlagen.";
var cpuPleaseWait$7 = "Bitte warten · der Test läuft";
var cpuScale$7 = "SMU-Skala";
var cpuStatusUnavailable$7 = "Der geschützte CPU-Status konnte nicht gelesen werden.";
var cpuTarget$7 = "Ziel";
var cpuTrial$7 = "SMU-Detektor · thermische Grenze";
var cpuVerifyAction$7 = "Führen Sie im aktuellen Startvorgang eine automatische Erkennung für genau diese Frequenz durch, bevor Sie ihn speichern.";
var cpuVerifyCause$7 = "Der Nachweis des Same-Boot-Detektors fehlt oder entspricht nicht der angeforderten Häufigkeit und Skalierung.";
var cpuVerifyFailed$7 = "Das CPU-Ergebnis konnte nicht überprüft werden.";
var cpuVidCeiling$7 = "1325 mV ist die absolute Obergrenze und kein empfohlener Zielwert. Upstream empfiehlt, unter 1300 mV zu bleiben.";
var cpuVoltage$7 = "Maximale VID";
var cuBackendAction$7 = "Bereiten Sie UMR im Desktop-Modus vor und synchronisieren Sie dann die Live-Karte CU erneut.";
var cuBackendCause$7 = "UMR, seine GPU-Datenbank oder der Live-Manager stimmen nicht mit dem laufenden Stack überein.";
var cuBackendFailed$7 = "Das Compute Units-Backend ist nicht bereit.";
var cuCause$7 = "Die angeforderte WGP-Karte und die Live-AMDGPU-Topologie stimmten nicht überein.";
var cuGuidance$7 = "Aktualisieren und überprüfen Sie die CU-Diagnose, wenn sie sich wiederholt.";
var cuOperationFailed$7 = "Der CU-Vorgang ist fehlgeschlagen.";
var current$7 = "AKTUELL";
var details$7 = "Technische Details";
var detected$7 = "Steuerung bereit";
var diagnosticCode$7 = "Diagnosecode";
var disabled$7 = "Deaktiviert";
var elapsed$7 = "Vergangen";
var enabled$7 = "Aktiviert";
var error$7 = "Die Änderung konnte nicht verifiziert werden";
var estimated$7 = "geschätzt";
var external$7 = "Topologie außerhalb des Schnellzugriffs geändert.";
var fan$7 = "VENTILATOR";
var fanCause$7 = "Der NCT-Treiber, die hwmon-Route, der PWM-Kanal oder das Schreib-Rücklesen sind nicht verfügbar.";
var fanGuidance$7 = "Setzen Sie den Kanal wieder auf „Automatisch“ und versuchen Sie es erneut.";
var fanOperationFailed$7 = "Der Lüfterbetrieb ist fehlgeschlagen.";
var fanRpmObserved$7 = "RPMbeobachtet";
var fanUnverified$7 = "Verkabelung nicht überprüft";
var fanWiring$7 = "PWM 2 ist der Standardkanal; Überprüfen Sie die Pumpen-/Lüfterverkabelung, bevor Sie eine manuelle Geschwindigkeit anwenden.";
var governorConflict$7 = "Cyan und Oberon sind beide aktiv. Stoppen Sie einen im Desktop-Modus.";
var governorMissing$7 = "Aktivieren Sie Cyan oder Oberon im Desktop-Modus.";
var gpuAction$7 = "Aktualisieren Sie den GPU-Status und überprüfen Sie den aktiven Gouverneur im Desktop-Modus.";
var gpuBusyCause$7 = "Die GPU befindet sich nicht im Ruhezustand, der für diese Oberon-Änderung erforderlich ist.";
var gpuBusyGuidance$7 = "Warten Sie, bis die GPU wieder auf 1000 MHz zurückkehrt, und versuchen Sie es dann erneut.";
var gpuCause$7 = "Der aktive Gouverneur oder der Live-Hardwarestatus haben die angeforderte Änderung nicht überprüft.";
var gpuDbusAction$7 = "Lassen Sie im Desktop-Modus einen Regler aktiv und warten Sie, bis für D-Bus Verbunden angezeigt wird.";
var gpuDbusCause$7 = "Cyan ist gestoppt, startet noch, ist falsch konfiguriert oder steht in Konflikt mit Oberon.";
var gpuDbusFailed$7 = "Die GPU-Governor-Steuerelemente sind nicht bereit.";
var gpuLive$7 = "Live-GPU";
var gpuOperationFailed$7 = "Der GPU-Vorgang ist fehlgeschlagen.";
var gpuRangeAction$7 = "Aktualisieren Sie und wählen Sie eines der aktuell angezeigten GPU-Profile oder sicheren Punkte aus.";
var gpuRangeCause$7 = "Der angeforderte Punkt liegt außerhalb der vom aktiven Gouverneur gemeldeten sicheren Tabelle.";
var gpuRangeFailed$7 = "Der ausgewählte GPU-Bereich wird derzeit nicht unterstützt.";
var gpuVoltage$7 = "Spannung";
var helperAction$7 = "Installieren Sie das BC250 Control Center im Desktop-Modus neu und reparieren Sie den Schnellzugriff.";
var helperCause$7 = "Der Helfer fehlt, hat den falschen Root-Besitz oder kann von einem anderen Benutzer geändert werden.";
var helperFailed$7 = "Der geschützte BC250-Helper fehlt oder ist unsicher.";
var hide$7 = "Details ausblenden";
var install$7 = "Dienst installieren";
var installExactProfile$7 = "Es wird nur das genaue Profil installiert, das während dieses Startvorgangs angewendet und überprüft wurde.";
var keep$7 = "Ziel behalten";
var likelyCause$7 = "Wahrscheinliche Ursache";
var liveRoutingUnchanged$7 = "Das Live-Routing ändert sich nicht.";
var loadingCpu$7 = "CPU-Helfer und Telemetrie werden gelesen…";
var loadingTopology$7 = "WGP-Topologie wird gelesen…";
var manualApplyWarning$7 = "Es wird vorübergehend mit der vom Detektor validierten Frequenz angewendet. Überwachen Sie Temperatur und Stabilität, bevor Sie den Dienst installieren.";
var memory$7 = "SPEICHER";
var more$7 = "Mehr Frequenzen";
var next$7 = "Nächster Schritt";
var oberonBusy$7 = "Warten Sie, bis die GPU wieder auf 1000 MHz zurückkehrt";
var oberonIdle$7 = "Nur Leerlaufwechsel";
var oberonReady$7 = "Bereit zur Veränderung";
var pending$7 = "ausstehend";
var profileBalanced$7 = "Ausgewogen";
var profileBenchmark$7 = "Benchmark";
var profileGaming$7 = "Spielen";
var profileRecovery$7 = "Erholung";
var protocolAction$7 = "Reparieren Sie den Schnellzugriff im Desktop-Modus und starten Sie dann den Decky Loader neu.";
var protocolCause$7 = "Nur ein Teil des BC250 Control Centers wurde aktualisiert, oder Decky ließ einen älteren Plugin-Prozess weiterlaufen.";
var protocolFailed$7 = "Quick Access und sein Helfer sind unterschiedliche Versionen.";
var readOnly$7 = "schreibgeschützt";
var remove$7 = "Dienst entfernen";
var restore$7 = "Live-Status wiederherstellen";
var retryGuidance$7 = "Warten Sie einige Sekunden und versuchen Sie es erneut.";
var runAutomaticFirst$7 = "Führen Sie zuerst die automatische Skalierung durch";
var safeCuMinimum$7 = "Der Schnellzugriff hält mindestens 24 CU sicher.";
var safeRange$7 = "validierter Bereich";
var save$7 = "Auswahl speichern";
var serviceRemovedBootProfile$7 = "Der Dienst wird entfernt; Das erkannte Profil bleibt während dieses Startvorgangs verfügbar.";
var snapshotWarning$7 = "Der freigegebene CU-Snapshot konnte nicht aktualisiert werden. Aktualisieren Sie, bevor Sie eine weitere CU-Änderung vornehmen.";
var speed$7 = "PWM-Geschwindigkeit";
var stale$7 = "Daten sind veraltet";
var stressMissing$7 = "Die von bc250-detect geforderte Stressabhängigkeit fehlt.";
var success$7 = "Änderung bestätigt";
var target$7 = "CU-Ziel";
var timeoutAction$7 = "Überprüfen Sie den Desktop-Modus auf einen laufenden Prozess oder Dienstfehler, bevor Sie es erneut versuchen.";
var timeoutCause$7 = "Ein Hilfsprogramm, ein Dienst, ein Hardware-Rücklesetool oder ein externes Toolkit reagiert nicht mehr.";
var timeoutFailed$7 = "Der Vorgang hat sein Sicherheitszeitlimit überschritten.";
var topologyUnavailable$7 = "WGP-Topologie nicht verfügbar.";
var ttmLimit$7 = "TTM-Limit";
var unavailable$7 = "nicht verfügbar";
var unknownCause$7 = "Quick Access hat einen Fehler erhalten, der noch nicht mit einer bekannten Komponente übereinstimmt.";
var voltageHint$7 = "echter bc250-detect-Eingang";
var zram$7 = "ZRAM";
var zswap$7 = "ZSWAP";
var de = {
	advanced: advanced$7,
	apply: apply$7,
	applyChanges: applyChanges$7,
	automatic: automatic$7,
	automaticApplyWarning: automaticApplyWarning$7,
	backingSwap: backingSwap$7,
	busyAction: busyAction$7,
	busyCause: busyCause$7,
	busyFailed: busyFailed$7,
	channel: channel$7,
	close: close$7,
	compute: compute$7,
	cpuApplyAuto: cpuApplyAuto$7,
	cpuApplyManual: cpuApplyManual$7,
	cpuApplying: cpuApplying$7,
	cpuCause: cpuCause$7,
	cpuDetectHelp: cpuDetectHelp$7,
	cpuDetected: cpuDetected$7,
	cpuFrequency: cpuFrequency$7,
	cpuGuidance: cpuGuidance$7,
	cpuHelperUnavailable: cpuHelperUnavailable$7,
	cpuLiveClock: cpuLiveClock$7,
	cpuManual: cpuManual$7,
	cpuManualHelp: cpuManualHelp$7,
	cpuNeedsDetection: cpuNeedsDetection$7,
	cpuOperationFailed: cpuOperationFailed$7,
	cpuPleaseWait: cpuPleaseWait$7,
	cpuScale: cpuScale$7,
	cpuStatusUnavailable: cpuStatusUnavailable$7,
	cpuTarget: cpuTarget$7,
	cpuTrial: cpuTrial$7,
	cpuVerifyAction: cpuVerifyAction$7,
	cpuVerifyCause: cpuVerifyCause$7,
	cpuVerifyFailed: cpuVerifyFailed$7,
	cpuVidCeiling: cpuVidCeiling$7,
	cpuVoltage: cpuVoltage$7,
	cuBackendAction: cuBackendAction$7,
	cuBackendCause: cuBackendCause$7,
	cuBackendFailed: cuBackendFailed$7,
	cuCause: cuCause$7,
	cuGuidance: cuGuidance$7,
	cuOperationFailed: cuOperationFailed$7,
	current: current$7,
	details: details$7,
	detected: detected$7,
	diagnosticCode: diagnosticCode$7,
	disabled: disabled$7,
	elapsed: elapsed$7,
	enabled: enabled$7,
	error: error$7,
	estimated: estimated$7,
	external: external$7,
	fan: fan$7,
	fanCause: fanCause$7,
	fanGuidance: fanGuidance$7,
	fanOperationFailed: fanOperationFailed$7,
	fanRpmObserved: fanRpmObserved$7,
	fanUnverified: fanUnverified$7,
	fanWiring: fanWiring$7,
	governorConflict: governorConflict$7,
	governorMissing: governorMissing$7,
	gpuAction: gpuAction$7,
	gpuBusyCause: gpuBusyCause$7,
	gpuBusyGuidance: gpuBusyGuidance$7,
	gpuCause: gpuCause$7,
	gpuDbusAction: gpuDbusAction$7,
	gpuDbusCause: gpuDbusCause$7,
	gpuDbusFailed: gpuDbusFailed$7,
	gpuLive: gpuLive$7,
	gpuOperationFailed: gpuOperationFailed$7,
	gpuRangeAction: gpuRangeAction$7,
	gpuRangeCause: gpuRangeCause$7,
	gpuRangeFailed: gpuRangeFailed$7,
	gpuVoltage: gpuVoltage$7,
	helperAction: helperAction$7,
	helperCause: helperCause$7,
	helperFailed: helperFailed$7,
	hide: hide$7,
	install: install$7,
	installExactProfile: installExactProfile$7,
	keep: keep$7,
	likelyCause: likelyCause$7,
	liveRoutingUnchanged: liveRoutingUnchanged$7,
	loadingCpu: loadingCpu$7,
	loadingTopology: loadingTopology$7,
	manualApplyWarning: manualApplyWarning$7,
	memory: memory$7,
	more: more$7,
	next: next$7,
	oberonBusy: oberonBusy$7,
	oberonIdle: oberonIdle$7,
	oberonReady: oberonReady$7,
	pending: pending$7,
	profileBalanced: profileBalanced$7,
	profileBenchmark: profileBenchmark$7,
	profileGaming: profileGaming$7,
	profileRecovery: profileRecovery$7,
	protocolAction: protocolAction$7,
	protocolCause: protocolCause$7,
	protocolFailed: protocolFailed$7,
	readOnly: readOnly$7,
	remove: remove$7,
	restore: restore$7,
	retryGuidance: retryGuidance$7,
	runAutomaticFirst: runAutomaticFirst$7,
	safeCuMinimum: safeCuMinimum$7,
	safeRange: safeRange$7,
	save: save$7,
	serviceRemovedBootProfile: serviceRemovedBootProfile$7,
	snapshotWarning: snapshotWarning$7,
	speed: speed$7,
	stale: stale$7,
	stressMissing: stressMissing$7,
	success: success$7,
	target: target$7,
	timeoutAction: timeoutAction$7,
	timeoutCause: timeoutCause$7,
	timeoutFailed: timeoutFailed$7,
	topologyUnavailable: topologyUnavailable$7,
	ttmLimit: ttmLimit$7,
	unavailable: unavailable$7,
	unknownCause: unknownCause$7,
	voltageHint: voltageHint$7,
	zram: zram$7,
	zswap: zswap$7
};

var advanced$6 = "advanced";
var apply$6 = "Apply";
var applyChanges$6 = "Apply changes";
var automatic$6 = "Automatic";
var automaticApplyWarning$6 = "bc250-detect will test the CPU under load, derive the scale, and apply only the result it finds. Monitor temperatures and stability.";
var backingSwap$6 = "Disk swap";
var busyAction$6 = "Wait for the current operation to finish, refresh, and retry once.";
var busyCause$6 = "A previous press, Desktop workflow, or external toolkit still holds the hardware lock.";
var busyFailed$6 = "Another BC250 operation is still running.";
var channel$6 = "PWM channel";
var close$6 = "Dismiss";
var compute$6 = "COMPUTE UNITS";
var cpuApplyAuto$6 = "Apply OC · automatic scale";
var cpuApplyManual$6 = "Apply OC · manual scale";
var cpuApplying$6 = "Applying CPU overclock";
var cpuCause$6 = "The detector, stress dependency, SMU helper, or selected profile did not complete safely.";
var cpuDetectHelp$6 = "Calibrates under load and applies the exact result";
var cpuDetected$6 = "Detected result";
var cpuFrequency$6 = "Target frequency";
var cpuGuidance$6 = "Review the validated profile in Desktop Mode.";
var cpuHelperUnavailable$6 = "The protected CPU helper is unavailable.";
var cpuLiveClock$6 = "Live frequency";
var cpuManual$6 = "Manual scale";
var cpuManualHelp$6 = "Requires automatic detection at this frequency";
var cpuNeedsDetection$6 = "Run temporary detection before applying or saving a profile.";
var cpuOperationFailed$6 = "The CPU operation failed.";
var cpuPleaseWait$6 = "Please wait · the test is running";
var cpuScale$6 = "SMU scale";
var cpuStatusUnavailable$6 = "The protected CPU state could not be read.";
var cpuTarget$6 = "Target";
var cpuTrial$6 = "SMU detector · thermal limit";
var cpuVerifyAction$6 = "Run automatic detection for this exact frequency in the current boot before saving it.";
var cpuVerifyCause$6 = "The same-boot detector evidence is missing or does not match the requested frequency and scale.";
var cpuVerifyFailed$6 = "The CPU result could not be verified.";
var cpuVidCeiling$6 = "1325 mV is the absolute ceiling, not a recommended target. Upstream recommends staying below 1300 mV.";
var cpuVoltage$6 = "Maximum VID";
var cuBackendAction$6 = "Prepare UMR in Desktop Mode, then sync the live CU map again.";
var cuBackendCause$6 = "UMR, its GPU database, or the live manager does not match the running stack.";
var cuBackendFailed$6 = "The Compute Units backend is not ready.";
var cuCause$6 = "The requested WGP map and the live AMDGPU topology did not agree.";
var cuGuidance$6 = "Refresh and review CU diagnostics if it repeats.";
var cuOperationFailed$6 = "The CU operation failed.";
var current$6 = "CURRENT";
var details$6 = "Technical details";
var detected$6 = "control ready";
var diagnosticCode$6 = "Diagnostic code";
var disabled$6 = "Disabled";
var elapsed$6 = "Elapsed";
var enabled$6 = "Enabled";
var error$6 = "The change could not be verified";
var estimated$6 = "estimated";
var external$6 = "Topology changed outside Quick Access.";
var fan$6 = "FAN";
var fanCause$6 = "The NCT driver, hwmon route, PWM channel, or write read-back is unavailable.";
var fanGuidance$6 = "Return the channel to Automatic and retry.";
var fanOperationFailed$6 = "The fan operation failed.";
var fanRpmObserved$6 = "RPM observed";
var fanUnverified$6 = "wiring unverified";
var fanWiring$6 = "PWM 2 is the default channel; confirm pump/fan wiring before applying a manual speed.";
var governorConflict$6 = "Cyan and Oberon are both active. Stop one in Desktop Mode.";
var governorMissing$6 = "Enable Cyan or Oberon in Desktop Mode.";
var gpuAction$6 = "Refresh GPU status and verify the active governor in Desktop Mode.";
var gpuBusyCause$6 = "The GPU is not at the idle state required for this Oberon change.";
var gpuBusyGuidance$6 = "Wait for the GPU to return to 1000 MHz, then retry.";
var gpuCause$6 = "The active governor or live hardware state did not verify the requested change.";
var gpuDbusAction$6 = "In Desktop Mode, keep one governor active and wait for D-Bus to show Connected.";
var gpuDbusCause$6 = "Cyan is stopped, still starting, misconfigured, or conflicting with Oberon.";
var gpuDbusFailed$6 = "The GPU governor controls are not ready.";
var gpuLive$6 = "Live GPU";
var gpuOperationFailed$6 = "The GPU operation failed.";
var gpuRangeAction$6 = "Refresh and choose one of the GPU profiles or safe points currently displayed.";
var gpuRangeCause$6 = "The requested point is outside the safe table reported by the active governor.";
var gpuRangeFailed$6 = "The selected GPU range is not supported now.";
var gpuVoltage$6 = "Voltage";
var helperAction$6 = "Reinstall BC250 Control Center from Desktop Mode and repair Quick Access.";
var helperCause$6 = "The helper is absent, has incorrect root ownership, or can be modified by another user.";
var helperFailed$6 = "The protected BC250 helper is missing or unsafe.";
var hide$6 = "Hide details";
var install$6 = "Install service";
var installExactProfile$6 = "Only the exact profile applied and verified during this boot will be installed.";
var keep$6 = "Keep target";
var likelyCause$6 = "Likely cause";
var liveRoutingUnchanged$6 = "Live routing will not change.";
var loadingCpu$6 = "Reading CPU helper and telemetry…";
var loadingTopology$6 = "Reading WGP topology…";
var manualApplyWarning$6 = "It will be applied temporarily at the detector-validated frequency. Monitor temperature and stability before installing the service.";
var memory$6 = "MEMORY";
var more$6 = "More frequencies";
var next$6 = "Next step";
var oberonBusy$6 = "Wait for the GPU to return to 1000 MHz";
var oberonIdle$6 = "Idle changes only";
var oberonReady$6 = "Ready to change";
var pending$6 = "pending";
var profileBalanced$6 = "Balanced";
var profileBenchmark$6 = "Benchmark";
var profileGaming$6 = "Gaming";
var profileRecovery$6 = "Recovery";
var protocolAction$6 = "Repair Quick Access in Desktop Mode, then restart Decky Loader.";
var protocolCause$6 = "Only part of BC250 Control Center was updated, or Decky kept an older plugin process running.";
var protocolFailed$6 = "Quick Access and its helper are different versions.";
var readOnly$6 = "read only";
var remove$6 = "Remove service";
var restore$6 = "Restore live state";
var retryGuidance$6 = "Wait a few seconds and retry.";
var runAutomaticFirst$6 = "Run automatic scale first";
var safeCuMinimum$6 = "Quick Access keeps a safe 24 CU minimum.";
var safeRange$6 = "validated range";
var save$6 = "Save selection";
var serviceRemovedBootProfile$6 = "The service is removed; the detected profile remains available during this boot.";
var snapshotWarning$6 = "The shared CU snapshot could not be updated. Refresh before making another CU change.";
var speed$6 = "PWM speed";
var stale$6 = "Data is stale";
var stressMissing$6 = "The stress dependency required by bc250-detect is missing.";
var success$6 = "Change verified";
var target$6 = "CU target";
var timeoutAction$6 = "Check Desktop Mode for a running process or service error before retrying.";
var timeoutCause$6 = "A helper, service, hardware read-back, or external toolkit stopped responding.";
var timeoutFailed$6 = "The operation exceeded its safety time limit.";
var topologyUnavailable$6 = "WGP topology unavailable.";
var ttmLimit$6 = "TTM limit";
var unavailable$6 = "unavailable";
var unknownCause$6 = "Quick Access received a failure that does not match a known component yet.";
var voltageHint$6 = "real bc250-detect input";
var zram$6 = "ZRAM";
var zswap$6 = "ZSWAP";
var en = {
	advanced: advanced$6,
	apply: apply$6,
	applyChanges: applyChanges$6,
	automatic: automatic$6,
	automaticApplyWarning: automaticApplyWarning$6,
	backingSwap: backingSwap$6,
	busyAction: busyAction$6,
	busyCause: busyCause$6,
	busyFailed: busyFailed$6,
	channel: channel$6,
	close: close$6,
	compute: compute$6,
	cpuApplyAuto: cpuApplyAuto$6,
	cpuApplyManual: cpuApplyManual$6,
	cpuApplying: cpuApplying$6,
	cpuCause: cpuCause$6,
	cpuDetectHelp: cpuDetectHelp$6,
	cpuDetected: cpuDetected$6,
	cpuFrequency: cpuFrequency$6,
	cpuGuidance: cpuGuidance$6,
	cpuHelperUnavailable: cpuHelperUnavailable$6,
	cpuLiveClock: cpuLiveClock$6,
	cpuManual: cpuManual$6,
	cpuManualHelp: cpuManualHelp$6,
	cpuNeedsDetection: cpuNeedsDetection$6,
	cpuOperationFailed: cpuOperationFailed$6,
	cpuPleaseWait: cpuPleaseWait$6,
	cpuScale: cpuScale$6,
	cpuStatusUnavailable: cpuStatusUnavailable$6,
	cpuTarget: cpuTarget$6,
	cpuTrial: cpuTrial$6,
	cpuVerifyAction: cpuVerifyAction$6,
	cpuVerifyCause: cpuVerifyCause$6,
	cpuVerifyFailed: cpuVerifyFailed$6,
	cpuVidCeiling: cpuVidCeiling$6,
	cpuVoltage: cpuVoltage$6,
	cuBackendAction: cuBackendAction$6,
	cuBackendCause: cuBackendCause$6,
	cuBackendFailed: cuBackendFailed$6,
	cuCause: cuCause$6,
	cuGuidance: cuGuidance$6,
	cuOperationFailed: cuOperationFailed$6,
	current: current$6,
	details: details$6,
	detected: detected$6,
	diagnosticCode: diagnosticCode$6,
	disabled: disabled$6,
	elapsed: elapsed$6,
	enabled: enabled$6,
	error: error$6,
	estimated: estimated$6,
	external: external$6,
	fan: fan$6,
	fanCause: fanCause$6,
	fanGuidance: fanGuidance$6,
	fanOperationFailed: fanOperationFailed$6,
	fanRpmObserved: fanRpmObserved$6,
	fanUnverified: fanUnverified$6,
	fanWiring: fanWiring$6,
	governorConflict: governorConflict$6,
	governorMissing: governorMissing$6,
	gpuAction: gpuAction$6,
	gpuBusyCause: gpuBusyCause$6,
	gpuBusyGuidance: gpuBusyGuidance$6,
	gpuCause: gpuCause$6,
	gpuDbusAction: gpuDbusAction$6,
	gpuDbusCause: gpuDbusCause$6,
	gpuDbusFailed: gpuDbusFailed$6,
	gpuLive: gpuLive$6,
	gpuOperationFailed: gpuOperationFailed$6,
	gpuRangeAction: gpuRangeAction$6,
	gpuRangeCause: gpuRangeCause$6,
	gpuRangeFailed: gpuRangeFailed$6,
	gpuVoltage: gpuVoltage$6,
	helperAction: helperAction$6,
	helperCause: helperCause$6,
	helperFailed: helperFailed$6,
	hide: hide$6,
	install: install$6,
	installExactProfile: installExactProfile$6,
	keep: keep$6,
	likelyCause: likelyCause$6,
	liveRoutingUnchanged: liveRoutingUnchanged$6,
	loadingCpu: loadingCpu$6,
	loadingTopology: loadingTopology$6,
	manualApplyWarning: manualApplyWarning$6,
	memory: memory$6,
	more: more$6,
	next: next$6,
	oberonBusy: oberonBusy$6,
	oberonIdle: oberonIdle$6,
	oberonReady: oberonReady$6,
	pending: pending$6,
	profileBalanced: profileBalanced$6,
	profileBenchmark: profileBenchmark$6,
	profileGaming: profileGaming$6,
	profileRecovery: profileRecovery$6,
	protocolAction: protocolAction$6,
	protocolCause: protocolCause$6,
	protocolFailed: protocolFailed$6,
	readOnly: readOnly$6,
	remove: remove$6,
	restore: restore$6,
	retryGuidance: retryGuidance$6,
	runAutomaticFirst: runAutomaticFirst$6,
	safeCuMinimum: safeCuMinimum$6,
	safeRange: safeRange$6,
	save: save$6,
	serviceRemovedBootProfile: serviceRemovedBootProfile$6,
	snapshotWarning: snapshotWarning$6,
	speed: speed$6,
	stale: stale$6,
	stressMissing: stressMissing$6,
	success: success$6,
	target: target$6,
	timeoutAction: timeoutAction$6,
	timeoutCause: timeoutCause$6,
	timeoutFailed: timeoutFailed$6,
	topologyUnavailable: topologyUnavailable$6,
	ttmLimit: ttmLimit$6,
	unavailable: unavailable$6,
	unknownCause: unknownCause$6,
	voltageHint: voltageHint$6,
	zram: zram$6,
	zswap: zswap$6
};

var advanced$5 = "avanzado";
var apply$5 = "Aplicar";
var applyChanges$5 = "Aplicar cambios";
var automatic$5 = "Automático";
var automaticApplyWarning$5 = "bc250-detect probará la CPU bajo carga, derivará la escala y aplicará únicamente el resultado encontrado. Supervisa temperaturas y estabilidad.";
var backingSwap$5 = "Swap en disco";
var busyAction$5 = "Espera a que termine la operación, actualiza y vuelve a intentarlo una vez.";
var busyCause$5 = "Una acción anterior, un flujo de Escritorio o un toolkit externo mantiene ocupado el hardware.";
var busyFailed$5 = "Todavía hay otra operación de BC250 en ejecución.";
var channel$5 = "Canal PWM";
var close$5 = "Cerrar";
var compute$5 = "COMPUTE UNITS";
var cpuApplyAuto$5 = "Aplicar OC · escala automática";
var cpuApplyManual$5 = "Aplicar OC · escala manual";
var cpuApplying$5 = "Aplicando overclock de CPU";
var cpuCause$5 = "El detector, la dependencia stress, el helper SMU o el perfil elegido no terminaron de forma segura.";
var cpuDetectHelp$5 = "Calibra bajo carga y aplica el resultado exacto";
var cpuDetected$5 = "Resultado detectado";
var cpuFrequency$5 = "Frecuencia objetivo";
var cpuGuidance$5 = "Revisa el perfil validado en Modo Escritorio.";
var cpuHelperUnavailable$5 = "El helper CPU protegido no está disponible.";
var cpuLiveClock$5 = "Frecuencia en vivo";
var cpuManual$5 = "Escala manual";
var cpuManualHelp$5 = "Requiere una detección automática de esta frecuencia";
var cpuNeedsDetection$5 = "Ejecuta la detección temporal antes de aplicar o guardar un perfil.";
var cpuOperationFailed$5 = "Falló la operación de CPU.";
var cpuPleaseWait$5 = "Espera un momento · la prueba está ejecutándose";
var cpuScale$5 = "Escala SMU";
var cpuStatusUnavailable$5 = "No se pudo leer el estado protegido de CPU.";
var cpuTarget$5 = "Objetivo";
var cpuTrial$5 = "Detector SMU · límite térmico";
var cpuVerifyAction$5 = "Ejecuta la detección automática para esta frecuencia exacta durante el arranque actual antes de guardarla.";
var cpuVerifyCause$5 = "Falta la evidencia del detector de este arranque o no coincide con la frecuencia y escala solicitadas.";
var cpuVerifyFailed$5 = "No se pudo verificar el resultado de CPU.";
var cpuVidCeiling$5 = "1325 mV es el límite absoluto, no un objetivo recomendado. Upstream recomienda mantenerse por debajo de 1300 mV.";
var cpuVoltage$5 = "VID máximo";
var cuBackendAction$5 = "Prepara UMR en Modo Escritorio y vuelve a sincronizar el mapa CU vivo.";
var cuBackendCause$5 = "UMR, su base de datos GPU o el live manager no coinciden con el stack en ejecución.";
var cuBackendFailed$5 = "El backend de Unidades de Cómputo no está listo.";
var cuCause$5 = "El mapa WGP solicitado y la topología AMDGPU en vivo no coincidieron.";
var cuGuidance$5 = "Actualiza el estado y revisa Diagnóstico CU si se repite.";
var cuOperationFailed$5 = "Falló la operación de CU.";
var current$5 = "ACTUAL";
var details$5 = "Detalles técnicos";
var detected$5 = "control listo";
var diagnosticCode$5 = "Código de diagnóstico";
var disabled$5 = "Inactivo";
var elapsed$5 = "Tiempo";
var enabled$5 = "Activo";
var error$5 = "No se pudo verificar el cambio";
var estimated$5 = "estimados";
var external$5 = "La topología cambió fuera de Quick Access.";
var fan$5 = "VENTILADOR";
var fanCause$5 = "El driver NCT, la ruta hwmon, el canal PWM o la verificación de escritura no están disponibles.";
var fanGuidance$5 = "Devuelve el canal a Automático y vuelve a intentarlo.";
var fanOperationFailed$5 = "Falló la operación del ventilador.";
var fanRpmObserved$5 = "RPM observadas";
var fanUnverified$5 = "cableado sin verificar";
var fanWiring$5 = "PWM 2 es el canal predeterminado; confirma el cableado de bomba/ventilador antes de aplicar una velocidad manual.";
var governorConflict$5 = "Cyan y Oberon están activos. Detén uno desde Modo Escritorio.";
var governorMissing$5 = "Activa Cyan u Oberon desde Modo Escritorio.";
var gpuAction$5 = "Actualiza el estado de GPU y verifica el governor activo en Modo Escritorio.";
var gpuBusyCause$5 = "La GPU no está en el estado de reposo requerido para este cambio de Oberon.";
var gpuBusyGuidance$5 = "Espera a que la GPU vuelva a 1000 MHz y reintenta.";
var gpuCause$5 = "El governor activo o el estado vivo del hardware no verificó el cambio solicitado.";
var gpuDbusAction$5 = "En Modo Escritorio deja un solo governor activo y espera a que D-Bus indique Conectado.";
var gpuDbusCause$5 = "Cyan está detenido, iniciando, mal configurado o en conflicto con Oberon.";
var gpuDbusFailed$5 = "Los controles del governor de GPU todavía no están listos.";
var gpuLive$5 = "GPU en vivo";
var gpuOperationFailed$5 = "Falló la operación de GPU.";
var gpuRangeAction$5 = "Actualiza y elige uno de los perfiles o puntos seguros de GPU mostrados.";
var gpuRangeCause$5 = "El punto solicitado queda fuera de la tabla segura informada por el governor activo.";
var gpuRangeFailed$5 = "El rango de GPU seleccionado no es compatible ahora.";
var gpuVoltage$5 = "Voltaje";
var helperAction$5 = "Reinstala BC250 Control Center desde Modo Escritorio y repara Quick Access.";
var helperCause$5 = "El helper no existe, no pertenece a root o puede ser modificado por otro usuario.";
var helperFailed$5 = "El helper protegido de BC250 falta o no es seguro.";
var hide$5 = "Ocultar detalles";
var install$5 = "Instalar servicio";
var installExactProfile$5 = "Se instalará exactamente el perfil aplicado y verificado en este arranque.";
var keep$5 = "Conservar objetivo";
var likelyCause$5 = "Causa probable";
var liveRoutingUnchanged$5 = "El ruteo vivo no cambiará.";
var loadingCpu$5 = "Leyendo helper y telemetría de CPU…";
var loadingTopology$5 = "Leyendo topología WGP…";
var manualApplyWarning$5 = "Se aplicará temporalmente sobre la frecuencia validada por el detector. Supervisa temperatura y estabilidad antes de instalar el servicio.";
var memory$5 = "MEMORIA";
var more$5 = "Más frecuencias";
var next$5 = "Siguiente paso";
var oberonBusy$5 = "Espera a que la GPU vuelva a 1000 MHz";
var oberonIdle$5 = "Cambios solo en reposo";
var oberonReady$5 = "Listo para cambiar";
var pending$5 = "pendiente";
var profileBalanced$5 = "Equilibrado";
var profileBenchmark$5 = "Benchmark";
var profileGaming$5 = "Juegos";
var profileRecovery$5 = "Recuperación";
var protocolAction$5 = "Repara Quick Access en Modo Escritorio y reinicia Decky Loader.";
var protocolCause$5 = "Solo se actualizó una parte de BC250 Control Center o Decky mantuvo un proceso antiguo del plugin.";
var protocolFailed$5 = "Quick Access y su helper tienen versiones diferentes.";
var readOnly$5 = "solo lectura";
var remove$5 = "Eliminar servicio";
var restore$5 = "Restaurar estado vivo";
var retryGuidance$5 = "Espera unos segundos y vuelve a intentarlo.";
var runAutomaticFirst$5 = "Ejecuta primero la escala automática";
var safeCuMinimum$5 = "Quick Access mantiene un mínimo seguro de 24 CU.";
var safeRange$5 = "rango validado";
var save$5 = "Guardar selección";
var serviceRemovedBootProfile$5 = "Se elimina el servicio; el perfil detectado se conserva durante este arranque.";
var snapshotWarning$5 = "No se pudo actualizar la instantánea CU compartida. Actualiza antes de realizar otro cambio CU.";
var speed$5 = "Velocidad PWM";
var stale$5 = "Datos desactualizados";
var stressMissing$5 = "Falta la dependencia stress para ejecutar bc250-detect.";
var success$5 = "Cambio verificado";
var target$5 = "CU objetivo";
var timeoutAction$5 = "Revisa en Modo Escritorio si sigue un proceso activo o existe un error de servicio.";
var timeoutCause$5 = "Un helper, servicio, lectura del hardware o toolkit externo dejó de responder.";
var timeoutFailed$5 = "La operación superó su límite de tiempo seguro.";
var topologyUnavailable$5 = "Topología WGP no disponible.";
var ttmLimit$5 = "Límite TTM";
var unavailable$5 = "no disponible";
var unknownCause$5 = "Quick Access recibió un fallo que todavía no coincide con un componente conocido.";
var voltageHint$5 = "entrada real de bc250-detect";
var zram$5 = "ZRAM";
var zswap$5 = "ZSWAP";
var es = {
	advanced: advanced$5,
	apply: apply$5,
	applyChanges: applyChanges$5,
	automatic: automatic$5,
	automaticApplyWarning: automaticApplyWarning$5,
	backingSwap: backingSwap$5,
	busyAction: busyAction$5,
	busyCause: busyCause$5,
	busyFailed: busyFailed$5,
	channel: channel$5,
	close: close$5,
	compute: compute$5,
	cpuApplyAuto: cpuApplyAuto$5,
	cpuApplyManual: cpuApplyManual$5,
	cpuApplying: cpuApplying$5,
	cpuCause: cpuCause$5,
	cpuDetectHelp: cpuDetectHelp$5,
	cpuDetected: cpuDetected$5,
	cpuFrequency: cpuFrequency$5,
	cpuGuidance: cpuGuidance$5,
	cpuHelperUnavailable: cpuHelperUnavailable$5,
	cpuLiveClock: cpuLiveClock$5,
	cpuManual: cpuManual$5,
	cpuManualHelp: cpuManualHelp$5,
	cpuNeedsDetection: cpuNeedsDetection$5,
	cpuOperationFailed: cpuOperationFailed$5,
	cpuPleaseWait: cpuPleaseWait$5,
	cpuScale: cpuScale$5,
	cpuStatusUnavailable: cpuStatusUnavailable$5,
	cpuTarget: cpuTarget$5,
	cpuTrial: cpuTrial$5,
	cpuVerifyAction: cpuVerifyAction$5,
	cpuVerifyCause: cpuVerifyCause$5,
	cpuVerifyFailed: cpuVerifyFailed$5,
	cpuVidCeiling: cpuVidCeiling$5,
	cpuVoltage: cpuVoltage$5,
	cuBackendAction: cuBackendAction$5,
	cuBackendCause: cuBackendCause$5,
	cuBackendFailed: cuBackendFailed$5,
	cuCause: cuCause$5,
	cuGuidance: cuGuidance$5,
	cuOperationFailed: cuOperationFailed$5,
	current: current$5,
	details: details$5,
	detected: detected$5,
	diagnosticCode: diagnosticCode$5,
	disabled: disabled$5,
	elapsed: elapsed$5,
	enabled: enabled$5,
	error: error$5,
	estimated: estimated$5,
	external: external$5,
	fan: fan$5,
	fanCause: fanCause$5,
	fanGuidance: fanGuidance$5,
	fanOperationFailed: fanOperationFailed$5,
	fanRpmObserved: fanRpmObserved$5,
	fanUnverified: fanUnverified$5,
	fanWiring: fanWiring$5,
	governorConflict: governorConflict$5,
	governorMissing: governorMissing$5,
	gpuAction: gpuAction$5,
	gpuBusyCause: gpuBusyCause$5,
	gpuBusyGuidance: gpuBusyGuidance$5,
	gpuCause: gpuCause$5,
	gpuDbusAction: gpuDbusAction$5,
	gpuDbusCause: gpuDbusCause$5,
	gpuDbusFailed: gpuDbusFailed$5,
	gpuLive: gpuLive$5,
	gpuOperationFailed: gpuOperationFailed$5,
	gpuRangeAction: gpuRangeAction$5,
	gpuRangeCause: gpuRangeCause$5,
	gpuRangeFailed: gpuRangeFailed$5,
	gpuVoltage: gpuVoltage$5,
	helperAction: helperAction$5,
	helperCause: helperCause$5,
	helperFailed: helperFailed$5,
	hide: hide$5,
	install: install$5,
	installExactProfile: installExactProfile$5,
	keep: keep$5,
	likelyCause: likelyCause$5,
	liveRoutingUnchanged: liveRoutingUnchanged$5,
	loadingCpu: loadingCpu$5,
	loadingTopology: loadingTopology$5,
	manualApplyWarning: manualApplyWarning$5,
	memory: memory$5,
	more: more$5,
	next: next$5,
	oberonBusy: oberonBusy$5,
	oberonIdle: oberonIdle$5,
	oberonReady: oberonReady$5,
	pending: pending$5,
	profileBalanced: profileBalanced$5,
	profileBenchmark: profileBenchmark$5,
	profileGaming: profileGaming$5,
	profileRecovery: profileRecovery$5,
	protocolAction: protocolAction$5,
	protocolCause: protocolCause$5,
	protocolFailed: protocolFailed$5,
	readOnly: readOnly$5,
	remove: remove$5,
	restore: restore$5,
	retryGuidance: retryGuidance$5,
	runAutomaticFirst: runAutomaticFirst$5,
	safeCuMinimum: safeCuMinimum$5,
	safeRange: safeRange$5,
	save: save$5,
	serviceRemovedBootProfile: serviceRemovedBootProfile$5,
	snapshotWarning: snapshotWarning$5,
	speed: speed$5,
	stale: stale$5,
	stressMissing: stressMissing$5,
	success: success$5,
	target: target$5,
	timeoutAction: timeoutAction$5,
	timeoutCause: timeoutCause$5,
	timeoutFailed: timeoutFailed$5,
	topologyUnavailable: topologyUnavailable$5,
	ttmLimit: ttmLimit$5,
	unavailable: unavailable$5,
	unknownCause: unknownCause$5,
	voltageHint: voltageHint$5,
	zram: zram$5,
	zswap: zswap$5
};

var advanced$4 = "avanzado";
var apply$4 = "Aplicar";
var applyChanges$4 = "Aplicar cambios";
var automatic$4 = "Automático";
var automaticApplyWarning$4 = "bc250-detect probará la CPU bajo carga, derivará la escala y aplicará únicamente el resultado encontrado. Supervisa temperaturas y estabilidad.";
var backingSwap$4 = "Swap en disco";
var busyAction$4 = "Espera a que termine la operación, actualiza y vuelve a intentarlo una vez.";
var busyCause$4 = "Una acción anterior, un flujo de Escritorio o un toolkit externo mantiene ocupado el hardware.";
var busyFailed$4 = "Todavía hay otra operación de BC250 en ejecución.";
var channel$4 = "Canal PWM";
var close$4 = "Cerrar";
var compute$4 = "COMPUTE UNITS";
var cpuApplyAuto$4 = "Aplicar OC · escala automática";
var cpuApplyManual$4 = "Aplicar OC · escala manual";
var cpuApplying$4 = "Aplicando overclock de CPU";
var cpuCause$4 = "El detector, la dependencia stress, el helper SMU o el perfil elegido no terminaron de forma segura.";
var cpuDetectHelp$4 = "Calibra bajo carga y aplica el resultado exacto";
var cpuDetected$4 = "Resultado detectado";
var cpuFrequency$4 = "Frecuencia objetivo";
var cpuGuidance$4 = "Revisa el perfil validado en Modo Escritorio.";
var cpuHelperUnavailable$4 = "El helper CPU protegido no está disponible.";
var cpuLiveClock$4 = "Frecuencia en vivo";
var cpuManual$4 = "Escala manual";
var cpuManualHelp$4 = "Requiere una detección automática de esta frecuencia";
var cpuNeedsDetection$4 = "Ejecuta la detección temporal antes de aplicar o guardar un perfil.";
var cpuOperationFailed$4 = "Falló la operación de CPU.";
var cpuPleaseWait$4 = "Espera un momento · la prueba está ejecutándose";
var cpuScale$4 = "Escala SMU";
var cpuStatusUnavailable$4 = "No se pudo leer el estado protegido de CPU.";
var cpuTarget$4 = "Objetivo";
var cpuTrial$4 = "Detector SMU · límite térmico";
var cpuVerifyAction$4 = "Ejecuta la detección automática para esta frecuencia exacta durante el arranque actual antes de guardarla.";
var cpuVerifyCause$4 = "Falta la evidencia del detector de este arranque o no coincide con la frecuencia y escala solicitadas.";
var cpuVerifyFailed$4 = "No se pudo verificar el resultado de CPU.";
var cpuVidCeiling$4 = "1325 mV es el límite absoluto, no un objetivo recomendado. Upstream recomienda mantenerse por debajo de 1300 mV.";
var cpuVoltage$4 = "VID máximo";
var cuBackendAction$4 = "Prepara UMR en Modo Escritorio y vuelve a sincronizar el mapa CU vivo.";
var cuBackendCause$4 = "UMR, su base de datos GPU o el live manager no coinciden con el stack en ejecución.";
var cuBackendFailed$4 = "El backend de Unidades de Cómputo no está listo.";
var cuCause$4 = "El mapa WGP solicitado y la topología AMDGPU en vivo no coincidieron.";
var cuGuidance$4 = "Actualiza el estado y revisa Diagnóstico CU si se repite.";
var cuOperationFailed$4 = "Falló la operación de CU.";
var current$4 = "ACTUAL";
var details$4 = "Detalles técnicos";
var detected$4 = "control listo";
var diagnosticCode$4 = "Código de diagnóstico";
var disabled$4 = "Inactivo";
var elapsed$4 = "Tiempo";
var enabled$4 = "Activo";
var error$4 = "No se pudo verificar el cambio";
var estimated$4 = "estimados";
var external$4 = "La topología cambió fuera de Quick Access.";
var fan$4 = "VENTILADOR";
var fanCause$4 = "El driver NCT, la ruta hwmon, el canal PWM o la verificación de escritura no están disponibles.";
var fanGuidance$4 = "Devuelve el canal a Automático y vuelve a intentarlo.";
var fanOperationFailed$4 = "Falló la operación del ventilador.";
var fanRpmObserved$4 = "RPM observadas";
var fanUnverified$4 = "cableado sin verificar";
var fanWiring$4 = "PWM 2 es el canal predeterminado; confirma el cableado de bomba/ventilador antes de aplicar una velocidad manual.";
var governorConflict$4 = "Cyan y Oberon están activos. Detén uno desde Modo Escritorio.";
var governorMissing$4 = "Activa Cyan u Oberon desde Modo Escritorio.";
var gpuAction$4 = "Actualiza el estado de GPU y verifica el governor activo en Modo Escritorio.";
var gpuBusyCause$4 = "La GPU no está en el estado de reposo requerido para este cambio de Oberon.";
var gpuBusyGuidance$4 = "Espera a que la GPU vuelva a 1000 MHz y reintenta.";
var gpuCause$4 = "El governor activo o el estado vivo del hardware no verificó el cambio solicitado.";
var gpuDbusAction$4 = "En Modo Escritorio deja un solo governor activo y espera a que D-Bus indique Conectado.";
var gpuDbusCause$4 = "Cyan está detenido, iniciando, mal configurado o en conflicto con Oberon.";
var gpuDbusFailed$4 = "Los controles del governor de GPU todavía no están listos.";
var gpuLive$4 = "GPU en vivo";
var gpuOperationFailed$4 = "Falló la operación de GPU.";
var gpuRangeAction$4 = "Actualiza y elige uno de los perfiles o puntos seguros de GPU mostrados.";
var gpuRangeCause$4 = "El punto solicitado queda fuera de la tabla segura informada por el governor activo.";
var gpuRangeFailed$4 = "El rango de GPU seleccionado no es compatible ahora.";
var gpuVoltage$4 = "Voltaje";
var helperAction$4 = "Reinstala BC250 Control Center desde Modo Escritorio y repara Quick Access.";
var helperCause$4 = "El helper no existe, no pertenece a root o puede ser modificado por otro usuario.";
var helperFailed$4 = "El helper protegido de BC250 falta o no es seguro.";
var hide$4 = "Ocultar detalles";
var install$4 = "Instalar servicio";
var installExactProfile$4 = "Se instalará exactamente el perfil aplicado y verificado en este arranque.";
var keep$4 = "Conservar objetivo";
var likelyCause$4 = "Causa probable";
var liveRoutingUnchanged$4 = "El ruteo vivo no cambiará.";
var loadingCpu$4 = "Leyendo helper y telemetría de CPU…";
var loadingTopology$4 = "Leyendo topología WGP…";
var manualApplyWarning$4 = "Se aplicará temporalmente sobre la frecuencia validada por el detector. Supervisa temperatura y estabilidad antes de instalar el servicio.";
var memory$4 = "MEMORIA";
var more$4 = "Más frecuencias";
var next$4 = "Siguiente paso";
var oberonBusy$4 = "Espera a que la GPU vuelva a 1000 MHz";
var oberonIdle$4 = "Cambios solo en reposo";
var oberonReady$4 = "Listo para cambiar";
var pending$4 = "pendiente";
var profileBalanced$4 = "Equilibrado";
var profileBenchmark$4 = "Benchmark";
var profileGaming$4 = "Juegos";
var profileRecovery$4 = "Recuperación";
var protocolAction$4 = "Repara Quick Access en Modo Escritorio y reinicia Decky Loader.";
var protocolCause$4 = "Solo se actualizó una parte de BC250 Control Center o Decky mantuvo un proceso antiguo del plugin.";
var protocolFailed$4 = "Quick Access y su helper tienen versiones diferentes.";
var readOnly$4 = "solo lectura";
var remove$4 = "Eliminar servicio";
var restore$4 = "Restaurar estado vivo";
var retryGuidance$4 = "Espera unos segundos y vuelve a intentarlo.";
var runAutomaticFirst$4 = "Ejecuta primero la escala automática";
var safeCuMinimum$4 = "Quick Access mantiene un mínimo seguro de 24 CU.";
var safeRange$4 = "rango validado";
var save$4 = "Guardar selección";
var serviceRemovedBootProfile$4 = "Se elimina el servicio; el perfil detectado se conserva durante este arranque.";
var snapshotWarning$4 = "No se pudo actualizar la instantánea CU compartida. Actualiza antes de realizar otro cambio CU.";
var speed$4 = "Velocidad PWM";
var stale$4 = "Datos desactualizados";
var stressMissing$4 = "Falta la dependencia stress para ejecutar bc250-detect.";
var success$4 = "Cambio verificado";
var target$4 = "CU objetivo";
var timeoutAction$4 = "Revisa en Modo Escritorio si sigue un proceso activo o existe un error de servicio.";
var timeoutCause$4 = "Un helper, servicio, lectura del hardware o toolkit externo dejó de responder.";
var timeoutFailed$4 = "La operación superó su límite de tiempo seguro.";
var topologyUnavailable$4 = "Topología WGP no disponible.";
var ttmLimit$4 = "Límite TTM";
var unavailable$4 = "no disponible";
var unknownCause$4 = "Quick Access recibió un fallo que todavía no coincide con un componente conocido.";
var voltageHint$4 = "entrada real de bc250-detect";
var zram$4 = "ZRAM";
var zswap$4 = "ZSWAP";
var es419 = {
	advanced: advanced$4,
	apply: apply$4,
	applyChanges: applyChanges$4,
	automatic: automatic$4,
	automaticApplyWarning: automaticApplyWarning$4,
	backingSwap: backingSwap$4,
	busyAction: busyAction$4,
	busyCause: busyCause$4,
	busyFailed: busyFailed$4,
	channel: channel$4,
	close: close$4,
	compute: compute$4,
	cpuApplyAuto: cpuApplyAuto$4,
	cpuApplyManual: cpuApplyManual$4,
	cpuApplying: cpuApplying$4,
	cpuCause: cpuCause$4,
	cpuDetectHelp: cpuDetectHelp$4,
	cpuDetected: cpuDetected$4,
	cpuFrequency: cpuFrequency$4,
	cpuGuidance: cpuGuidance$4,
	cpuHelperUnavailable: cpuHelperUnavailable$4,
	cpuLiveClock: cpuLiveClock$4,
	cpuManual: cpuManual$4,
	cpuManualHelp: cpuManualHelp$4,
	cpuNeedsDetection: cpuNeedsDetection$4,
	cpuOperationFailed: cpuOperationFailed$4,
	cpuPleaseWait: cpuPleaseWait$4,
	cpuScale: cpuScale$4,
	cpuStatusUnavailable: cpuStatusUnavailable$4,
	cpuTarget: cpuTarget$4,
	cpuTrial: cpuTrial$4,
	cpuVerifyAction: cpuVerifyAction$4,
	cpuVerifyCause: cpuVerifyCause$4,
	cpuVerifyFailed: cpuVerifyFailed$4,
	cpuVidCeiling: cpuVidCeiling$4,
	cpuVoltage: cpuVoltage$4,
	cuBackendAction: cuBackendAction$4,
	cuBackendCause: cuBackendCause$4,
	cuBackendFailed: cuBackendFailed$4,
	cuCause: cuCause$4,
	cuGuidance: cuGuidance$4,
	cuOperationFailed: cuOperationFailed$4,
	current: current$4,
	details: details$4,
	detected: detected$4,
	diagnosticCode: diagnosticCode$4,
	disabled: disabled$4,
	elapsed: elapsed$4,
	enabled: enabled$4,
	error: error$4,
	estimated: estimated$4,
	external: external$4,
	fan: fan$4,
	fanCause: fanCause$4,
	fanGuidance: fanGuidance$4,
	fanOperationFailed: fanOperationFailed$4,
	fanRpmObserved: fanRpmObserved$4,
	fanUnverified: fanUnverified$4,
	fanWiring: fanWiring$4,
	governorConflict: governorConflict$4,
	governorMissing: governorMissing$4,
	gpuAction: gpuAction$4,
	gpuBusyCause: gpuBusyCause$4,
	gpuBusyGuidance: gpuBusyGuidance$4,
	gpuCause: gpuCause$4,
	gpuDbusAction: gpuDbusAction$4,
	gpuDbusCause: gpuDbusCause$4,
	gpuDbusFailed: gpuDbusFailed$4,
	gpuLive: gpuLive$4,
	gpuOperationFailed: gpuOperationFailed$4,
	gpuRangeAction: gpuRangeAction$4,
	gpuRangeCause: gpuRangeCause$4,
	gpuRangeFailed: gpuRangeFailed$4,
	gpuVoltage: gpuVoltage$4,
	helperAction: helperAction$4,
	helperCause: helperCause$4,
	helperFailed: helperFailed$4,
	hide: hide$4,
	install: install$4,
	installExactProfile: installExactProfile$4,
	keep: keep$4,
	likelyCause: likelyCause$4,
	liveRoutingUnchanged: liveRoutingUnchanged$4,
	loadingCpu: loadingCpu$4,
	loadingTopology: loadingTopology$4,
	manualApplyWarning: manualApplyWarning$4,
	memory: memory$4,
	more: more$4,
	next: next$4,
	oberonBusy: oberonBusy$4,
	oberonIdle: oberonIdle$4,
	oberonReady: oberonReady$4,
	pending: pending$4,
	profileBalanced: profileBalanced$4,
	profileBenchmark: profileBenchmark$4,
	profileGaming: profileGaming$4,
	profileRecovery: profileRecovery$4,
	protocolAction: protocolAction$4,
	protocolCause: protocolCause$4,
	protocolFailed: protocolFailed$4,
	readOnly: readOnly$4,
	remove: remove$4,
	restore: restore$4,
	retryGuidance: retryGuidance$4,
	runAutomaticFirst: runAutomaticFirst$4,
	safeCuMinimum: safeCuMinimum$4,
	safeRange: safeRange$4,
	save: save$4,
	serviceRemovedBootProfile: serviceRemovedBootProfile$4,
	snapshotWarning: snapshotWarning$4,
	speed: speed$4,
	stale: stale$4,
	stressMissing: stressMissing$4,
	success: success$4,
	target: target$4,
	timeoutAction: timeoutAction$4,
	timeoutCause: timeoutCause$4,
	timeoutFailed: timeoutFailed$4,
	topologyUnavailable: topologyUnavailable$4,
	ttmLimit: ttmLimit$4,
	unavailable: unavailable$4,
	unknownCause: unknownCause$4,
	voltageHint: voltageHint$4,
	zram: zram$4,
	zswap: zswap$4
};

var advanced$3 = "zaawansowany";
var apply$3 = "Zastosuj";
var applyChanges$3 = "Zastosuj zmiany";
var automatic$3 = "Automatyczny";
var automaticApplyWarning$3 = "bc250-detect przetestuje CPU pod obciążeniem, obliczy skalę i zastosuje tylko znaleziony wynik. Monitoruj temperaturę i stabilność.";
var backingSwap$3 = "Wymiana dysku";
var busyAction$3 = "Poczekaj na zakończenie bieżącej operacji, odśwież i spróbuj jeszcze raz.";
var busyCause$3 = "Poprzednie naciśnięcie, przepływ pracy na komputerze stacjonarnym lub zewnętrzny zestaw narzędzi nadal powodują blokadę sprzętową.";
var busyFailed$3 = "Inna operacja BC250 jest nadal wykonywana.";
var channel$3 = "Kanał PWM";
var close$3 = "Odrzuć";
var compute$3 = "JEDNOSTKI OBLICZENIOWE";
var cpuApplyAuto$3 = "Zastosuj OC · automatyczna skala";
var cpuApplyManual$3 = "Zastosuj OC · skala ręczna";
var cpuApplying$3 = "Stosowanie podkręcania CPU";
var cpuCause$3 = "Detektor, zależność od stresu, pomocnik SMU lub wybrany profil nie zakończyły się pomyślnie.";
var cpuDetectHelp$3 = "Kalibruje pod obciążeniem i stosuje dokładny wynik";
var cpuDetected$3 = "Wykryty wynik";
var cpuFrequency$3 = "Częstotliwość docelowa";
var cpuGuidance$3 = "Przejrzyj zatwierdzony profil w trybie pulpitu.";
var cpuHelperUnavailable$3 = "Chroniony moduł pomocniczy CPU jest niedostępny.";
var cpuLiveClock$3 = "Częstotliwość na żywo";
var cpuManual$3 = "Skala ręczna";
var cpuManualHelp$3 = "Wymaga automatycznego wykrywania przy tej częstotliwości";
var cpuNeedsDetection$3 = "Uruchom tymczasowe wykrywanie przed zastosowaniem lub zapisaniem profilu.";
var cpuOperationFailed$3 = "Operacja CPU nie powiodła się.";
var cpuPleaseWait$3 = "Proszę czekać · test trwa";
var cpuScale$3 = "Skala SMU";
var cpuStatusUnavailable$3 = "Nie można odczytać chronionego stanu CPU.";
var cpuTarget$3 = "Cel";
var cpuTrial$3 = "Detektor SMU · ograniczenie termiczne";
var cpuVerifyAction$3 = "Uruchom automatyczne wykrywanie dokładnie tej częstotliwości w bieżącym rozruchu przed jego zapisaniem.";
var cpuVerifyCause$3 = "Brak dowodów wykrywacza tego samego rozruchu lub nie odpowiadają one żądanej częstotliwości i skali.";
var cpuVerifyFailed$3 = "Nie można zweryfikować wyniku CPU.";
var cpuVidCeiling$3 = "1325 mV to absolutny pułap, a nie zalecany cel. Upstream zaleca pozostawanie poniżej 1300 mV.";
var cpuVoltage$3 = "Maksymalny VID";
var cuBackendAction$3 = "Przygotuj UMR w trybie pulpitu, a następnie ponownie zsynchronizuj aktualną mapę CU.";
var cuBackendCause$3 = "UMR, jego baza danych GPU lub menedżer na żywo nie pasują do działającego stosu.";
var cuBackendFailed$3 = "Zaplecze jednostek obliczeniowych nie jest gotowe.";
var cuCause$3 = "Żądana mapa WGP i działająca topologia AMDGPU nie są zgodne.";
var cuGuidance$3 = "Odśwież i przejrzyj diagnostykę CU, jeśli będzie się powtarzać.";
var cuOperationFailed$3 = "Operacja CU nie powiodła się.";
var current$3 = "AKTUALNE";
var details$3 = "Szczegóły techniczne";
var detected$3 = "kontrola gotowa";
var diagnosticCode$3 = "Kod diagnostyczny";
var disabled$3 = "Niepełnosprawny";
var elapsed$3 = "Upłynął";
var enabled$3 = "Włączony";
var error$3 = "Nie udało się zweryfikować zmiany";
var estimated$3 = "szacunkowy";
var external$3 = "Topologia zmieniona poza Szybkim dostępem.";
var fan$3 = "FAN";
var fanCause$3 = "Sterownik NCT, trasa hwmon, kanał PWM lub funkcja odczytu zapisu są niedostępne.";
var fanGuidance$3 = "Przywróć kanał do trybu automatycznego i spróbuj ponownie.";
var fanOperationFailed$3 = "Działanie wentylatora nie powiodło się.";
var fanRpmObserved$3 = "RPMzauważony";
var fanUnverified$3 = "okablowanie niezweryfikowane";
var fanWiring$3 = "PWM 2 jest kanałem domyślnym; przed zastosowaniem ręcznej prędkości sprawdź okablowanie pompy/wentylatora.";
var governorConflict$3 = "Zarówno Cyan, jak i Oberon są aktywne. Zatrzymaj jeden w trybie pulpitu.";
var governorMissing$3 = "Włącz opcję Cyan lub Oberon w trybie pulpitu.";
var gpuAction$3 = "Odśwież stan GPU i zweryfikuj aktywny zarządca w trybie pulpitu.";
var gpuBusyCause$3 = "GPU nie znajduje się w stanie bezczynności wymaganym do tej zmiany Oberon.";
var gpuBusyGuidance$3 = "Poczekaj, aż GPU powróci do 1000 MHz, a następnie spróbuj ponownie.";
var gpuCause$3 = "Aktywny gubernator lub stan aktywnego sprzętu nie zweryfikował żądanej zmiany.";
var gpuDbusAction$3 = "W trybie stacjonarnym pozostaw aktywny jeden regulator i poczekaj, aż D-Bus wyświetli komunikat Połączono.";
var gpuDbusCause$3 = "Cyan jest zatrzymany, nadal się uruchamia, jest błędnie skonfigurowany lub powoduje konflikt z Oberon.";
var gpuDbusFailed$3 = "Elementy sterujące GPU nie są gotowe.";
var gpuLive$3 = "Na żywo GPU";
var gpuOperationFailed$3 = "Operacja GPU nie powiodła się.";
var gpuRangeAction$3 = "Odśwież i wybierz jeden z aktualnie wyświetlanych profili GPU lub bezpiecznych punktów.";
var gpuRangeCause$3 = "Żądany punkt znajduje się poza bezpieczną tabelą zgłoszoną przez aktywnego gubernatora.";
var gpuRangeFailed$3 = "Wybrany zakres GPU nie jest teraz obsługiwany.";
var gpuVoltage$3 = "Napięcie";
var helperAction$3 = "Zainstaluj ponownie Centrum sterowania BC250 z trybu pulpitu i napraw Szybki dostęp.";
var helperCause$3 = "Pomocnik jest nieobecny, ma nieprawidłowe uprawnienia roota lub może zostać zmodyfikowany przez innego użytkownika.";
var helperFailed$3 = "Brak chronionego programu pomocniczego BC250 lub jest on niebezpieczny.";
var hide$3 = "Ukryj szczegóły";
var install$3 = "Zainstaluj usługę";
var installExactProfile$3 = "Zainstalowany zostanie tylko dokładnie ten profil, który został zastosowany i zweryfikowany podczas tego rozruchu.";
var keep$3 = "Utrzymuj cel";
var likelyCause$3 = "Prawdopodobna przyczyna";
var liveRoutingUnchanged$3 = "Trasowanie na żywo nie ulegnie zmianie.";
var loadingCpu$3 = "Odczytywanie pomocnika CPU i danych telemetrycznych…";
var loadingTopology$3 = "Odczytywanie topologii WGP…";
var manualApplyWarning$3 = "Zostanie ono zastosowane tymczasowo z częstotliwością zatwierdzoną przez detektor. Przed zainstalowaniem usługi monitoruj temperaturę i stabilność.";
var memory$3 = "PAMIĘĆ";
var more$3 = "Więcej częstotliwości";
var next$3 = "Następny krok";
var oberonBusy$3 = "Poczekaj, aż GPU powróci do 1000 MHz";
var oberonIdle$3 = "Tylko bezczynne zmiany";
var oberonReady$3 = "Gotowy na zmianę";
var pending$3 = "w toku";
var profileBalanced$3 = "Zrównoważony";
var profileBenchmark$3 = "Punkt odniesienia";
var profileGaming$3 = "Gry";
var profileRecovery$3 = "Odzyskiwanie";
var protocolAction$3 = "Napraw Szybki dostęp w trybie pulpitu, a następnie uruchom ponownie moduł ładujący Decky.";
var protocolCause$3 = "Zaktualizowano tylko część Centrum sterowania BC250 lub Decky pozostawił działający starszy proces wtyczek.";
var protocolFailed$3 = "Szybki dostęp i jego pomocnik to różne wersje.";
var readOnly$3 = "tylko czytać";
var remove$3 = "Usuń usługę";
var restore$3 = "Przywróć stan aktywny";
var retryGuidance$3 = "Poczekaj kilka sekund i spróbuj ponownie.";
var runAutomaticFirst$3 = "Najpierw uruchom automatyczne skalowanie";
var safeCuMinimum$3 = "Szybki dostęp zapewnia bezpieczne minimum 24 CU.";
var safeRange$3 = "zatwierdzony zakres";
var save$3 = "Zapisz wybór";
var serviceRemovedBootProfile$3 = "Usługa zostaje usunięta; wykryty profil pozostaje dostępny podczas tego rozruchu.";
var snapshotWarning$3 = "Nie można zaktualizować udostępnionej migawki CU. Odśwież przed wprowadzeniem kolejnej zmiany CU.";
var speed$3 = "Prędkość PWM";
var stale$3 = "Dane są nieaktualne";
var stressMissing$3 = "Brak zależności naprężenia wymaganej przez program bc250-detect.";
var success$3 = "Zmiana zweryfikowana";
var target$3 = "Cel CU";
var timeoutAction$3 = "Przed ponowną próbą sprawdź tryb pulpitu pod kątem działającego procesu lub błędu usługi.";
var timeoutCause$3 = "Pomocnik, usługa, odczyt zwrotny sprzętu lub zewnętrzny zestaw narzędzi przestały odpowiadać.";
var timeoutFailed$3 = "Operacja przekroczyła limit czasu bezpieczeństwa.";
var topologyUnavailable$3 = "Topologia WGP jest niedostępna.";
var ttmLimit$3 = "Limit TTM";
var unavailable$3 = "niedostępne";
var unknownCause$3 = "Szybki dostęp otrzymał błąd, który nie pasuje jeszcze do znanego komponentu.";
var voltageHint$3 = "prawdziwe wejście wykrywające bc250";
var zram$3 = "ZRAM";
var zswap$3 = "ZSWAP";
var pl = {
	advanced: advanced$3,
	apply: apply$3,
	applyChanges: applyChanges$3,
	automatic: automatic$3,
	automaticApplyWarning: automaticApplyWarning$3,
	backingSwap: backingSwap$3,
	busyAction: busyAction$3,
	busyCause: busyCause$3,
	busyFailed: busyFailed$3,
	channel: channel$3,
	close: close$3,
	compute: compute$3,
	cpuApplyAuto: cpuApplyAuto$3,
	cpuApplyManual: cpuApplyManual$3,
	cpuApplying: cpuApplying$3,
	cpuCause: cpuCause$3,
	cpuDetectHelp: cpuDetectHelp$3,
	cpuDetected: cpuDetected$3,
	cpuFrequency: cpuFrequency$3,
	cpuGuidance: cpuGuidance$3,
	cpuHelperUnavailable: cpuHelperUnavailable$3,
	cpuLiveClock: cpuLiveClock$3,
	cpuManual: cpuManual$3,
	cpuManualHelp: cpuManualHelp$3,
	cpuNeedsDetection: cpuNeedsDetection$3,
	cpuOperationFailed: cpuOperationFailed$3,
	cpuPleaseWait: cpuPleaseWait$3,
	cpuScale: cpuScale$3,
	cpuStatusUnavailable: cpuStatusUnavailable$3,
	cpuTarget: cpuTarget$3,
	cpuTrial: cpuTrial$3,
	cpuVerifyAction: cpuVerifyAction$3,
	cpuVerifyCause: cpuVerifyCause$3,
	cpuVerifyFailed: cpuVerifyFailed$3,
	cpuVidCeiling: cpuVidCeiling$3,
	cpuVoltage: cpuVoltage$3,
	cuBackendAction: cuBackendAction$3,
	cuBackendCause: cuBackendCause$3,
	cuBackendFailed: cuBackendFailed$3,
	cuCause: cuCause$3,
	cuGuidance: cuGuidance$3,
	cuOperationFailed: cuOperationFailed$3,
	current: current$3,
	details: details$3,
	detected: detected$3,
	diagnosticCode: diagnosticCode$3,
	disabled: disabled$3,
	elapsed: elapsed$3,
	enabled: enabled$3,
	error: error$3,
	estimated: estimated$3,
	external: external$3,
	fan: fan$3,
	fanCause: fanCause$3,
	fanGuidance: fanGuidance$3,
	fanOperationFailed: fanOperationFailed$3,
	fanRpmObserved: fanRpmObserved$3,
	fanUnverified: fanUnverified$3,
	fanWiring: fanWiring$3,
	governorConflict: governorConflict$3,
	governorMissing: governorMissing$3,
	gpuAction: gpuAction$3,
	gpuBusyCause: gpuBusyCause$3,
	gpuBusyGuidance: gpuBusyGuidance$3,
	gpuCause: gpuCause$3,
	gpuDbusAction: gpuDbusAction$3,
	gpuDbusCause: gpuDbusCause$3,
	gpuDbusFailed: gpuDbusFailed$3,
	gpuLive: gpuLive$3,
	gpuOperationFailed: gpuOperationFailed$3,
	gpuRangeAction: gpuRangeAction$3,
	gpuRangeCause: gpuRangeCause$3,
	gpuRangeFailed: gpuRangeFailed$3,
	gpuVoltage: gpuVoltage$3,
	helperAction: helperAction$3,
	helperCause: helperCause$3,
	helperFailed: helperFailed$3,
	hide: hide$3,
	install: install$3,
	installExactProfile: installExactProfile$3,
	keep: keep$3,
	likelyCause: likelyCause$3,
	liveRoutingUnchanged: liveRoutingUnchanged$3,
	loadingCpu: loadingCpu$3,
	loadingTopology: loadingTopology$3,
	manualApplyWarning: manualApplyWarning$3,
	memory: memory$3,
	more: more$3,
	next: next$3,
	oberonBusy: oberonBusy$3,
	oberonIdle: oberonIdle$3,
	oberonReady: oberonReady$3,
	pending: pending$3,
	profileBalanced: profileBalanced$3,
	profileBenchmark: profileBenchmark$3,
	profileGaming: profileGaming$3,
	profileRecovery: profileRecovery$3,
	protocolAction: protocolAction$3,
	protocolCause: protocolCause$3,
	protocolFailed: protocolFailed$3,
	readOnly: readOnly$3,
	remove: remove$3,
	restore: restore$3,
	retryGuidance: retryGuidance$3,
	runAutomaticFirst: runAutomaticFirst$3,
	safeCuMinimum: safeCuMinimum$3,
	safeRange: safeRange$3,
	save: save$3,
	serviceRemovedBootProfile: serviceRemovedBootProfile$3,
	snapshotWarning: snapshotWarning$3,
	speed: speed$3,
	stale: stale$3,
	stressMissing: stressMissing$3,
	success: success$3,
	target: target$3,
	timeoutAction: timeoutAction$3,
	timeoutCause: timeoutCause$3,
	timeoutFailed: timeoutFailed$3,
	topologyUnavailable: topologyUnavailable$3,
	ttmLimit: ttmLimit$3,
	unavailable: unavailable$3,
	unknownCause: unknownCause$3,
	voltageHint: voltageHint$3,
	zram: zram$3,
	zswap: zswap$3
};

var advanced$2 = "avançado";
var apply$2 = "Aplicar";
var applyChanges$2 = "Aplicar alterações";
var automatic$2 = "Automático";
var automaticApplyWarning$2 = "bc250-detect testará a CPU sob carga, derivará a escala e aplicará apenas o resultado encontrado. Monitore temperaturas e estabilidade.";
var backingSwap$2 = "Troca de disco";
var busyAction$2 = "Aguarde a conclusão da operação atual, atualize e tente novamente uma vez.";
var busyCause$2 = "Uma impressão anterior, fluxo de trabalho de desktop ou kit de ferramentas externo ainda mantém o bloqueio de hardware.";
var busyFailed$2 = "Outra operação BC250 ainda está em execução.";
var channel$2 = "Canal PWM";
var close$2 = "Dispensar";
var compute$2 = "UNIDADES DE COMPUTAÇÃO";
var cpuApplyAuto$2 = "Aplicar OC · escala automática";
var cpuApplyManual$2 = "Aplicar OC · escala manual";
var cpuApplying$2 = "Aplicando overclock de CPU";
var cpuCause$2 = "O detector, a dependência de estresse, o auxiliar SMU ou o perfil selecionado não foram concluídos com segurança.";
var cpuDetectHelp$2 = "Calibra sob carga e aplica o resultado exato";
var cpuDetected$2 = "Resultado detectado";
var cpuFrequency$2 = "Frequência-alvo";
var cpuGuidance$2 = "Revise o perfil validado no modo Desktop.";
var cpuHelperUnavailable$2 = "O auxiliar CPU protegido não está disponível.";
var cpuLiveClock$2 = "Frequência ao vivo";
var cpuManual$2 = "Escala manual";
var cpuManualHelp$2 = "Requer detecção automática nesta frequência";
var cpuNeedsDetection$2 = "Execute a detecção temporária antes de aplicar ou salvar um perfil.";
var cpuOperationFailed$2 = "A operação CPU falhou.";
var cpuPleaseWait$2 = "Aguarde · o teste está em execução";
var cpuScale$2 = "Escala SMU";
var cpuStatusUnavailable$2 = "O estado protegido da CPU não pôde ser lido.";
var cpuTarget$2 = "Alvo";
var cpuTrial$2 = "Detector SMU · limite térmico";
var cpuVerifyAction$2 = "Execute a detecção automática para esta frequência exata na inicialização atual antes de salvá-la.";
var cpuVerifyCause$2 = "A evidência do detector de mesma inicialização está faltando ou não corresponde à frequência e escala solicitadas.";
var cpuVerifyFailed$2 = "O resultado da CPU não pôde ser verificado.";
var cpuVidCeiling$2 = "1325 mV é o teto absoluto, não um alvo recomendado. Upstream recomenda ficar abaixo de 1300 mV.";
var cpuVoltage$2 = "VID máximo";
var cuBackendAction$2 = "Prepare o UMR no modo Desktop e, em seguida, sincronize o mapa CU ao vivo novamente.";
var cuBackendCause$2 = "UMR, seu banco de dados GPU ou o gerenciador ativo não corresponde à pilha em execução.";
var cuBackendFailed$2 = "O back-end do Compute Units não está pronto.";
var cuCause$2 = "O mapa WGP solicitado e a topologia AMDGPU ativa não concordaram.";
var cuGuidance$2 = "Atualize e revise o diagnóstico do CU se ele se repetir.";
var cuOperationFailed$2 = "A operação CU falhou.";
var current$2 = "ATUAL";
var details$2 = "Detalhes técnicos";
var detected$2 = "controle pronto";
var diagnosticCode$2 = "Código de diagnóstico";
var disabled$2 = "Desativado";
var elapsed$2 = "Decorrido";
var enabled$2 = "Habilitado";
var error$2 = "A alteração não pôde ser verificada";
var estimated$2 = "estimado";
var external$2 = "Topologia alterada fora do Acesso Rápido.";
var fan$2 = "VENTILADOR";
var fanCause$2 = "O driver NCT, a rota hwmon, o canal PWM ou a leitura de gravação não estão disponíveis.";
var fanGuidance$2 = "Retorne o canal para Automático e tente novamente.";
var fanOperationFailed$2 = "A operação do ventilador falhou.";
var fanRpmObserved$2 = "RPM observadas";
var fanUnverified$2 = "fiação não verificada";
var fanWiring$2 = "PWM 2 é o canal padrão; confirme a fiação da bomba/ventilador antes de aplicar uma velocidade manual.";
var governorConflict$2 = "Cyan e Oberon estão ambos ativos. Pare um no modo Desktop.";
var governorMissing$2 = "Habilite Cyan ou Oberon no modo Desktop.";
var gpuAction$2 = "Atualize o status da GPU e verifique o governador ativo no modo Desktop.";
var gpuBusyCause$2 = "A GPU não está no estado inativo necessário para esta alteração do Oberon.";
var gpuBusyGuidance$2 = "Aguarde até que a GPU retorne a 1000 MHz e tente novamente.";
var gpuCause$2 = "O governador ativo ou o estado do hardware ativo não verificou a alteração solicitada.";
var gpuDbusAction$2 = "No modo Desktop, mantenha um governador ativo e espere que D-Bus mostre Connected.";
var gpuDbusCause$2 = "Cyan está parado, ainda iniciando, configurado incorretamente ou em conflito com Oberon.";
var gpuDbusFailed$2 = "Os controles reguladores da GPU não estão prontos.";
var gpuLive$2 = "GPU ativa";
var gpuOperationFailed$2 = "A operação GPU falhou.";
var gpuRangeAction$2 = "Atualize e escolha um dos perfis GPU ou pontos seguros exibidos atualmente.";
var gpuRangeCause$2 = "O ponto solicitado está fora da tabela segura informada pelo governador ativo.";
var gpuRangeFailed$2 = "O intervalo de GPU selecionado não é suportado agora.";
var gpuVoltage$2 = "Voltagem";
var helperAction$2 = "Reinstale o BC250 Control Center no modo Desktop e repare o acesso rápido.";
var helperCause$2 = "O auxiliar está ausente, possui propriedade raiz incorreta ou pode ser modificado por outro usuário.";
var helperFailed$2 = "O auxiliar BC250 protegido está ausente ou não é seguro.";
var hide$2 = "Ocultar detalhes";
var install$2 = "Instalar serviço";
var installExactProfile$2 = "Somente o perfil exato aplicado e verificado durante esta inicialização será instalado.";
var keep$2 = "Mantenha a meta";
var likelyCause$2 = "Causa provável";
var liveRoutingUnchanged$2 = "O roteamento ao vivo não será alterado.";
var loadingCpu$2 = "Lendo auxiliar de CPU e telemetria…";
var loadingTopology$2 = "Lendo a topologia WGP…";
var manualApplyWarning$2 = "Será aplicado temporariamente na frequência validada pelo detector. Monitore a temperatura e a estabilidade antes de instalar o serviço.";
var memory$2 = "MEMÓRIA";
var more$2 = "Mais frequências";
var next$2 = "Próxima etapa";
var oberonBusy$2 = "Aguarde até que a GPU retorne a 1000 MHz";
var oberonIdle$2 = "Apenas alterações inativas";
var oberonReady$2 = "Pronto para mudar";
var pending$2 = "pendente";
var profileBalanced$2 = "Equilibrado";
var profileBenchmark$2 = "Referência";
var profileGaming$2 = "Jogos";
var profileRecovery$2 = "Recuperação";
var protocolAction$2 = "Repare o acesso rápido no modo desktop e reinicie o Decky Loader.";
var protocolCause$2 = "Apenas parte do BC250 Control Center foi atualizada ou Decky manteve um processo de plugin mais antigo em execução.";
var protocolFailed$2 = "O Acesso Rápido e seu auxiliar são versões diferentes.";
var readOnly$2 = "somente leitura";
var remove$2 = "Remover serviço";
var restore$2 = "Restaurar estado ativo";
var retryGuidance$2 = "Aguarde alguns segundos e tente novamente.";
var runAutomaticFirst$2 = "Execute a escala automática primeiro";
var safeCuMinimum$2 = "O Acesso Rápido mantém um mínimo seguro de 24 CU.";
var safeRange$2 = "intervalo validado";
var save$2 = "Salvar seleção";
var serviceRemovedBootProfile$2 = "O serviço é removido; o perfil detectado permanece disponível durante esta inicialização.";
var snapshotWarning$2 = "O instantâneo CU compartilhado não pôde ser atualizado. Atualize antes de fazer outra alteração no CU.";
var speed$2 = "Velocidade PWM";
var stale$2 = "Os dados estão obsoletos";
var stressMissing$2 = "A dependência de estresse exigida pelo bc250-detect está ausente.";
var success$2 = "Alteração verificada";
var target$2 = "CU destino";
var timeoutAction$2 = "Verifique o Modo Desktop para ver se há um processo em execução ou erro de serviço antes de tentar novamente.";
var timeoutCause$2 = "Um auxiliar, serviço, leitura de hardware ou kit de ferramentas externo parou de responder.";
var timeoutFailed$2 = "A operação ultrapassou o limite de tempo de segurança.";
var topologyUnavailable$2 = "Topologia WGP indisponível.";
var ttmLimit$2 = "Limite de TTM";
var unavailable$2 = "indisponível";
var unknownCause$2 = "O Acesso Rápido recebeu uma falha que ainda não corresponde a um componente conhecido.";
var voltageHint$2 = "entrada de detecção bc250 real";
var zram$2 = "ZRAM";
var zswap$2 = "ZSWAP";
var pt = {
	advanced: advanced$2,
	apply: apply$2,
	applyChanges: applyChanges$2,
	automatic: automatic$2,
	automaticApplyWarning: automaticApplyWarning$2,
	backingSwap: backingSwap$2,
	busyAction: busyAction$2,
	busyCause: busyCause$2,
	busyFailed: busyFailed$2,
	channel: channel$2,
	close: close$2,
	compute: compute$2,
	cpuApplyAuto: cpuApplyAuto$2,
	cpuApplyManual: cpuApplyManual$2,
	cpuApplying: cpuApplying$2,
	cpuCause: cpuCause$2,
	cpuDetectHelp: cpuDetectHelp$2,
	cpuDetected: cpuDetected$2,
	cpuFrequency: cpuFrequency$2,
	cpuGuidance: cpuGuidance$2,
	cpuHelperUnavailable: cpuHelperUnavailable$2,
	cpuLiveClock: cpuLiveClock$2,
	cpuManual: cpuManual$2,
	cpuManualHelp: cpuManualHelp$2,
	cpuNeedsDetection: cpuNeedsDetection$2,
	cpuOperationFailed: cpuOperationFailed$2,
	cpuPleaseWait: cpuPleaseWait$2,
	cpuScale: cpuScale$2,
	cpuStatusUnavailable: cpuStatusUnavailable$2,
	cpuTarget: cpuTarget$2,
	cpuTrial: cpuTrial$2,
	cpuVerifyAction: cpuVerifyAction$2,
	cpuVerifyCause: cpuVerifyCause$2,
	cpuVerifyFailed: cpuVerifyFailed$2,
	cpuVidCeiling: cpuVidCeiling$2,
	cpuVoltage: cpuVoltage$2,
	cuBackendAction: cuBackendAction$2,
	cuBackendCause: cuBackendCause$2,
	cuBackendFailed: cuBackendFailed$2,
	cuCause: cuCause$2,
	cuGuidance: cuGuidance$2,
	cuOperationFailed: cuOperationFailed$2,
	current: current$2,
	details: details$2,
	detected: detected$2,
	diagnosticCode: diagnosticCode$2,
	disabled: disabled$2,
	elapsed: elapsed$2,
	enabled: enabled$2,
	error: error$2,
	estimated: estimated$2,
	external: external$2,
	fan: fan$2,
	fanCause: fanCause$2,
	fanGuidance: fanGuidance$2,
	fanOperationFailed: fanOperationFailed$2,
	fanRpmObserved: fanRpmObserved$2,
	fanUnverified: fanUnverified$2,
	fanWiring: fanWiring$2,
	governorConflict: governorConflict$2,
	governorMissing: governorMissing$2,
	gpuAction: gpuAction$2,
	gpuBusyCause: gpuBusyCause$2,
	gpuBusyGuidance: gpuBusyGuidance$2,
	gpuCause: gpuCause$2,
	gpuDbusAction: gpuDbusAction$2,
	gpuDbusCause: gpuDbusCause$2,
	gpuDbusFailed: gpuDbusFailed$2,
	gpuLive: gpuLive$2,
	gpuOperationFailed: gpuOperationFailed$2,
	gpuRangeAction: gpuRangeAction$2,
	gpuRangeCause: gpuRangeCause$2,
	gpuRangeFailed: gpuRangeFailed$2,
	gpuVoltage: gpuVoltage$2,
	helperAction: helperAction$2,
	helperCause: helperCause$2,
	helperFailed: helperFailed$2,
	hide: hide$2,
	install: install$2,
	installExactProfile: installExactProfile$2,
	keep: keep$2,
	likelyCause: likelyCause$2,
	liveRoutingUnchanged: liveRoutingUnchanged$2,
	loadingCpu: loadingCpu$2,
	loadingTopology: loadingTopology$2,
	manualApplyWarning: manualApplyWarning$2,
	memory: memory$2,
	more: more$2,
	next: next$2,
	oberonBusy: oberonBusy$2,
	oberonIdle: oberonIdle$2,
	oberonReady: oberonReady$2,
	pending: pending$2,
	profileBalanced: profileBalanced$2,
	profileBenchmark: profileBenchmark$2,
	profileGaming: profileGaming$2,
	profileRecovery: profileRecovery$2,
	protocolAction: protocolAction$2,
	protocolCause: protocolCause$2,
	protocolFailed: protocolFailed$2,
	readOnly: readOnly$2,
	remove: remove$2,
	restore: restore$2,
	retryGuidance: retryGuidance$2,
	runAutomaticFirst: runAutomaticFirst$2,
	safeCuMinimum: safeCuMinimum$2,
	safeRange: safeRange$2,
	save: save$2,
	serviceRemovedBootProfile: serviceRemovedBootProfile$2,
	snapshotWarning: snapshotWarning$2,
	speed: speed$2,
	stale: stale$2,
	stressMissing: stressMissing$2,
	success: success$2,
	target: target$2,
	timeoutAction: timeoutAction$2,
	timeoutCause: timeoutCause$2,
	timeoutFailed: timeoutFailed$2,
	topologyUnavailable: topologyUnavailable$2,
	ttmLimit: ttmLimit$2,
	unavailable: unavailable$2,
	unknownCause: unknownCause$2,
	voltageHint: voltageHint$2,
	zram: zram$2,
	zswap: zswap$2
};

var advanced$1 = "продвинутый";
var apply$1 = "Применить";
var applyChanges$1 = "Применить изменения";
var automatic$1 = "Автоматический";
var automaticApplyWarning$1 = "bc250-detect проверит CPU под нагрузкой, определит масштаб и применит только найденный результат. Следите за температурой и стабильностью.";
var backingSwap$1 = "Замена диска";
var busyAction$1 = "Дождитесь завершения текущей операции, обновите ее и повторите попытку.";
var busyCause$1 = "Предыдущая печатная машина, рабочий процесс рабочего стола или внешний набор инструментов по-прежнему сохраняют аппаратную блокировку.";
var busyFailed$1 = "Другая операция BC250 все еще выполняется.";
var channel$1 = "Канал PWM";
var close$1 = "Уволить";
var compute$1 = "ВЫЧИСЛИТЕЛЬНЫЕ БЛОКИ";
var cpuApplyAuto$1 = "Применить OC · автоматическое масштабирование";
var cpuApplyManual$1 = "Применить OC · ручная шкала";
var cpuApplying$1 = "Применение разгона CPU";
var cpuCause$1 = "Детектор, зависимость стресса, помощник SMU или выбранный профиль не завершились безопасно.";
var cpuDetectHelp$1 = "Калибруется под нагрузкой и получает точный результат";
var cpuDetected$1 = "Обнаруженный результат";
var cpuFrequency$1 = "Целевая частота";
var cpuGuidance$1 = "Просмотрите проверенный профиль в режиме рабочего стола.";
var cpuHelperUnavailable$1 = "Защищенный помощник CPU недоступен.";
var cpuLiveClock$1 = "Живая частота";
var cpuManual$1 = "Ручная шкала";
var cpuManualHelp$1 = "Требуется автоматическое обнаружение на этой частоте";
var cpuNeedsDetection$1 = "Запустите временное обнаружение перед применением или сохранением профиля.";
var cpuOperationFailed$1 = "Не удалось выполнить операцию CPU.";
var cpuPleaseWait$1 = "Пожалуйста, подождите · тест идет";
var cpuScale$1 = "масштаб SMU";
var cpuStatusUnavailable$1 = "Не удалось прочитать состояние защищенного CPU.";
var cpuTarget$1 = "Цель";
var cpuTrial$1 = "Детектор SMU · температурный предел";
var cpuVerifyAction$1 = "Запустите автоматическое определение именно этой частоты в текущей загрузке перед ее сохранением.";
var cpuVerifyCause$1 = "Свидетельство детектора той же загрузки отсутствует или не соответствует запрошенной частоте и масштабу.";
var cpuVerifyFailed$1 = "Не удалось проверить результат CPU.";
var cpuVidCeiling$1 = "1325 мВ — это абсолютный потолок, а не рекомендуемая цель. Компания Upstream рекомендует оставаться ниже 1300 мВ.";
var cpuVoltage$1 = "Максимальный VID";
var cuBackendAction$1 = "Подготовьте UMR в режиме рабочего стола, а затем снова синхронизируйте действующую карту CU.";
var cuBackendCause$1 = "UMR, его база данных GPU или живой менеджер не соответствуют работающему стеку.";
var cuBackendFailed$1 = "Серверная часть Compute Units не готова.";
var cuCause$1 = "Запрошенная карта WGP и действующая топология AMDGPU не согласовались.";
var cuGuidance$1 = "Обновите и просмотрите диагностику CU, если она повторяется.";
var cuOperationFailed$1 = "Не удалось выполнить операцию CU.";
var current$1 = "ТЕКУЩЕЕ";
var details$1 = "Технические детали";
var detected$1 = "управление готово";
var diagnosticCode$1 = "Диагностический код";
var disabled$1 = "Отключено";
var elapsed$1 = "Прошедшее";
var enabled$1 = "Включён";
var error$1 = "Изменение не удалось подтвердить.";
var estimated$1 = "оцененный";
var external$1 = "Топология изменена за пределами быстрого доступа.";
var fan$1 = "ФАН";
var fanCause$1 = "Драйвер NCT, маршрут hwmon, канал PWM или обратная запись недоступны.";
var fanGuidance$1 = "Верните канал в автоматический режим и повторите попытку.";
var fanOperationFailed$1 = "Сбой в работе вентилятора.";
var fanRpmObserved$1 = "RPMнаблюдал";
var fanUnverified$1 = "проводка не проверена";
var fanWiring$1 = "PWM 2 — канал по умолчанию; проверьте проводку насоса/вентилятора перед применением ручной скорости.";
var governorConflict$1 = "Cyan и Oberon активны. Остановите один в режиме рабочего стола.";
var governorMissing$1 = "Включите Cyan или Oberon в режиме рабочего стола.";
var gpuAction$1 = "Обновите статус GPU и проверьте активный регулятор в режиме рабочего стола.";
var gpuBusyCause$1 = "GPU не находится в состоянии ожидания, необходимом для этого изменения Oberon.";
var gpuBusyGuidance$1 = "Подождите, пока GPU вернется к частоте 1000 МГц, затем повторите попытку.";
var gpuCause$1 = "Активный регулятор или рабочее состояние оборудования не подтвердили запрошенное изменение.";
var gpuDbusAction$1 = "В режиме рабочего стола оставьте один регулятор активным и подождите, пока D-Bus не отобразится «Подключено».";
var gpuDbusCause$1 = "Cyan остановлен, все еще запускается, неправильно настроен или конфликтует с Oberon.";
var gpuDbusFailed$1 = "Элементы управления регулятором GPU не готовы.";
var gpuLive$1 = "Живой GPU";
var gpuOperationFailed$1 = "Не удалось выполнить операцию GPU.";
var gpuRangeAction$1 = "Обновите и выберите один из профилей GPU или безопасных точек, отображаемых в данный момент.";
var gpuRangeCause$1 = "Запрошенная точка находится за пределами безопасной таблицы, о которой сообщает активный регулятор.";
var gpuRangeFailed$1 = "Выбранный диапазон GPU сейчас не поддерживается.";
var gpuVoltage$1 = "Напряжение";
var helperAction$1 = "Переустановите BC250 Центр управления из режима рабочего стола и восстановите быстрый доступ.";
var helperCause$1 = "Помощник отсутствует, имеет неправильный root-владелец или может быть изменен другим пользователем.";
var helperFailed$1 = "Защищенный помощник BC250 отсутствует или небезопасен.";
var hide$1 = "Скрыть детали";
var install$1 = "Установить службу";
var installExactProfile$1 = "Будет установлен только тот профиль, который был применен и проверен во время этой загрузки.";
var keep$1 = "Держите цель";
var likelyCause$1 = "Вероятная причина";
var liveRoutingUnchanged$1 = "Живая маршрутизация не изменится.";
var loadingCpu$1 = "Чтение помощника CPU и телеметрии…";
var loadingTopology$1 = "Чтение топологии WGP…";
var manualApplyWarning$1 = "Он будет временно применяться на частоте, подтвержденной детектором. Перед установкой сервиса следите за температурой и стабильностью.";
var memory$1 = "ПАМЯТЬ";
var more$1 = "Больше частот";
var next$1 = "Следующий шаг";
var oberonBusy$1 = "Подождите, пока GPU вернется к частоте 1000 МГц.";
var oberonIdle$1 = "Изменения только на холостом ходу";
var oberonReady$1 = "Готов измениться";
var pending$1 = "в ожидании";
var profileBalanced$1 = "Сбалансированный";
var profileBenchmark$1 = "Тест производительности";
var profileGaming$1 = "Игровой";
var profileRecovery$1 = "Восстановление";
var protocolAction$1 = "Восстановите быстрый доступ в режиме рабочего стола, затем перезапустите загрузчик Decky.";
var protocolCause$1 = "Была обновлена только часть Центра управления BC250, или Decky сохранил работу старого процесса плагина.";
var protocolFailed$1 = "Быстрый доступ и его помощник — это разные версии.";
var readOnly$1 = "только чтение";
var remove$1 = "Удалить службу";
var restore$1 = "Восстановить живое состояние";
var retryGuidance$1 = "Подождите несколько секунд и повторите попытку.";
var runAutomaticFirst$1 = "Сначала запустите автоматическое масштабирование";
var safeCuMinimum$1 = "Быстрый доступ обеспечивает безопасный минимум 24 CU.";
var safeRange$1 = "проверенный диапазон";
var save$1 = "Сохранить выбор";
var serviceRemovedBootProfile$1 = "Услуга удалена; обнаруженный профиль остается доступным во время этой загрузки.";
var snapshotWarning$1 = "Не удалось обновить общий снимок CU. Обновите перед внесением еще одного изменения CU.";
var speed$1 = "PWM скорость";
var stale$1 = "Данные устарели";
var stressMissing$1 = "Зависимость от напряжения, требуемая bc250-detect, отсутствует.";
var success$1 = "Изменение подтверждено";
var target$1 = "CU цель";
var timeoutAction$1 = "Прежде чем повторить попытку, проверьте режим рабочего стола на наличие ошибок запущенного процесса или службы.";
var timeoutCause$1 = "Помощник, служба, аппаратное средство обратного считывания или внешний набор инструментов перестали отвечать.";
var timeoutFailed$1 = "Операция превысила безопасный лимит времени.";
var topologyUnavailable$1 = "Топология WGP недоступна.";
var ttmLimit$1 = "Ограничение TTM";
var unavailable$1 = "недоступен";
var unknownCause$1 = "Быстрый доступ получил ошибку, которая еще не соответствует известному компоненту.";
var voltageHint$1 = "настоящий ввод bc250-обнаружения";
var zram$1 = "ZRAM";
var zswap$1 = "ZSWAP";
var ru = {
	advanced: advanced$1,
	apply: apply$1,
	applyChanges: applyChanges$1,
	automatic: automatic$1,
	automaticApplyWarning: automaticApplyWarning$1,
	backingSwap: backingSwap$1,
	busyAction: busyAction$1,
	busyCause: busyCause$1,
	busyFailed: busyFailed$1,
	channel: channel$1,
	close: close$1,
	compute: compute$1,
	cpuApplyAuto: cpuApplyAuto$1,
	cpuApplyManual: cpuApplyManual$1,
	cpuApplying: cpuApplying$1,
	cpuCause: cpuCause$1,
	cpuDetectHelp: cpuDetectHelp$1,
	cpuDetected: cpuDetected$1,
	cpuFrequency: cpuFrequency$1,
	cpuGuidance: cpuGuidance$1,
	cpuHelperUnavailable: cpuHelperUnavailable$1,
	cpuLiveClock: cpuLiveClock$1,
	cpuManual: cpuManual$1,
	cpuManualHelp: cpuManualHelp$1,
	cpuNeedsDetection: cpuNeedsDetection$1,
	cpuOperationFailed: cpuOperationFailed$1,
	cpuPleaseWait: cpuPleaseWait$1,
	cpuScale: cpuScale$1,
	cpuStatusUnavailable: cpuStatusUnavailable$1,
	cpuTarget: cpuTarget$1,
	cpuTrial: cpuTrial$1,
	cpuVerifyAction: cpuVerifyAction$1,
	cpuVerifyCause: cpuVerifyCause$1,
	cpuVerifyFailed: cpuVerifyFailed$1,
	cpuVidCeiling: cpuVidCeiling$1,
	cpuVoltage: cpuVoltage$1,
	cuBackendAction: cuBackendAction$1,
	cuBackendCause: cuBackendCause$1,
	cuBackendFailed: cuBackendFailed$1,
	cuCause: cuCause$1,
	cuGuidance: cuGuidance$1,
	cuOperationFailed: cuOperationFailed$1,
	current: current$1,
	details: details$1,
	detected: detected$1,
	diagnosticCode: diagnosticCode$1,
	disabled: disabled$1,
	elapsed: elapsed$1,
	enabled: enabled$1,
	error: error$1,
	estimated: estimated$1,
	external: external$1,
	fan: fan$1,
	fanCause: fanCause$1,
	fanGuidance: fanGuidance$1,
	fanOperationFailed: fanOperationFailed$1,
	fanRpmObserved: fanRpmObserved$1,
	fanUnverified: fanUnverified$1,
	fanWiring: fanWiring$1,
	governorConflict: governorConflict$1,
	governorMissing: governorMissing$1,
	gpuAction: gpuAction$1,
	gpuBusyCause: gpuBusyCause$1,
	gpuBusyGuidance: gpuBusyGuidance$1,
	gpuCause: gpuCause$1,
	gpuDbusAction: gpuDbusAction$1,
	gpuDbusCause: gpuDbusCause$1,
	gpuDbusFailed: gpuDbusFailed$1,
	gpuLive: gpuLive$1,
	gpuOperationFailed: gpuOperationFailed$1,
	gpuRangeAction: gpuRangeAction$1,
	gpuRangeCause: gpuRangeCause$1,
	gpuRangeFailed: gpuRangeFailed$1,
	gpuVoltage: gpuVoltage$1,
	helperAction: helperAction$1,
	helperCause: helperCause$1,
	helperFailed: helperFailed$1,
	hide: hide$1,
	install: install$1,
	installExactProfile: installExactProfile$1,
	keep: keep$1,
	likelyCause: likelyCause$1,
	liveRoutingUnchanged: liveRoutingUnchanged$1,
	loadingCpu: loadingCpu$1,
	loadingTopology: loadingTopology$1,
	manualApplyWarning: manualApplyWarning$1,
	memory: memory$1,
	more: more$1,
	next: next$1,
	oberonBusy: oberonBusy$1,
	oberonIdle: oberonIdle$1,
	oberonReady: oberonReady$1,
	pending: pending$1,
	profileBalanced: profileBalanced$1,
	profileBenchmark: profileBenchmark$1,
	profileGaming: profileGaming$1,
	profileRecovery: profileRecovery$1,
	protocolAction: protocolAction$1,
	protocolCause: protocolCause$1,
	protocolFailed: protocolFailed$1,
	readOnly: readOnly$1,
	remove: remove$1,
	restore: restore$1,
	retryGuidance: retryGuidance$1,
	runAutomaticFirst: runAutomaticFirst$1,
	safeCuMinimum: safeCuMinimum$1,
	safeRange: safeRange$1,
	save: save$1,
	serviceRemovedBootProfile: serviceRemovedBootProfile$1,
	snapshotWarning: snapshotWarning$1,
	speed: speed$1,
	stale: stale$1,
	stressMissing: stressMissing$1,
	success: success$1,
	target: target$1,
	timeoutAction: timeoutAction$1,
	timeoutCause: timeoutCause$1,
	timeoutFailed: timeoutFailed$1,
	topologyUnavailable: topologyUnavailable$1,
	ttmLimit: ttmLimit$1,
	unavailable: unavailable$1,
	unknownCause: unknownCause$1,
	voltageHint: voltageHint$1,
	zram: zram$1,
	zswap: zswap$1
};

var advanced = "просунутий";
var apply = "Застосувати";
var applyChanges = "Застосувати зміни";
var automatic = "Автоматичний";
var automaticApplyWarning = "bc250-detect перевірить CPU під навантаженням, виведе масштаб і застосує лише знайдений результат. Слідкуйте за температурою та стабільністю.";
var backingSwap = "Заміна диска";
var busyAction = "Дочекайтеся завершення поточної операції, оновіть і повторіть спробу.";
var busyCause = "Попереднє натискання, робочий процес на робочому столі або зовнішній набір інструментів усе ще утримують апаратне блокування.";
var busyFailed = "Інша операція BC250 все ще виконується.";
var channel = "Канал PWM";
var close = "Відхилити";
var compute = "ОБЧИСЛЮВАЛЬНІ БЛОКИ";
var cpuApplyAuto = "Застосувати OC · автоматичний масштаб";
var cpuApplyManual = "Застосувати OC · ручну шкалу";
var cpuApplying = "Застосування розгону CPU";
var cpuCause = "Детектор, залежність від стресу, помічник SMU або вибраний профіль не завершилися безпечно.";
var cpuDetectHelp = "Калібрує під навантаженням і застосовує точний результат";
var cpuDetected = "Виявлений результат";
var cpuFrequency = "Цільова частота";
var cpuGuidance = "Перегляньте перевірений профіль у режимі настільного комп’ютера.";
var cpuHelperUnavailable = "Захищений помічник CPU недоступний.";
var cpuLiveClock = "Жива частота";
var cpuManual = "Ручна шкала";
var cpuManualHelp = "Потрібне автоматичне виявлення на цій частоті";
var cpuNeedsDetection = "Запустіть тимчасове виявлення перед застосуванням або збереженням профілю.";
var cpuOperationFailed = "Не вдалося виконати операцію CPU.";
var cpuPleaseWait = "Будь ласка, зачекайте · тест виконується";
var cpuScale = "Шкала SMU";
var cpuStatusUnavailable = "Неможливо прочитати стан захищеного CPU.";
var cpuTarget = "Ціль";
var cpuTrial = "Детектор SMU · теплова межа";
var cpuVerifyAction = "Запустіть автоматичне визначення для цієї точної частоти в поточному завантаженні, перш ніж зберегти його.";
var cpuVerifyCause = "Доказ детектора того самого завантаження відсутній або не відповідає запитаній частоті та масштабу.";
var cpuVerifyFailed = "Не вдалося перевірити результат CPU.";
var cpuVidCeiling = "1325 мВ — це абсолютна стеля, а не рекомендована ціль. Upstream рекомендує залишатися нижче 1300 мВ.";
var cpuVoltage = "Максимальний VID";
var cuBackendAction = "Підготуйте UMR у робочому режимі, а потім знову синхронізуйте живу карту CU.";
var cuBackendCause = "UMR, його база даних GPU або живий менеджер не відповідає запущеному стеку.";
var cuBackendFailed = "Сервер Compute Units не готовий.";
var cuCause = "Запитана карта WGP і активна топологія AMDGPU не узгоджуються.";
var cuGuidance = "Оновіть і перегляньте діагностику CU, якщо вона повторюється.";
var cuOperationFailed = "Не вдалося виконати операцію CU.";
var current = "ПОТОЧНЕ";
var details = "Технічні деталі";
var detected = "контроль готовий";
var diagnosticCode = "Діагностичний код";
var disabled = "Вимкнено";
var elapsed = "Минув";
var enabled = "Увімкнено";
var error = "Не вдалося перевірити зміну";
var estimated = "оцінюється";
var external = "Топологія змінена за межами швидкого доступу.";
var fan = "ВЕНТИЛЯТОР";
var fanCause = "Драйвер NCT, маршрут hwmon, канал PWM або зворотне записування недоступні.";
var fanGuidance = "Поверніть канал до автоматичного режиму та повторіть спробу.";
var fanOperationFailed = "Помилка роботи вентилятора.";
var fanRpmObserved = "RPMспостерігається";
var fanUnverified = "проводка неперевірена";
var fanWiring = "PWM 2 є каналом за замовчуванням; перевірте електропроводку насоса/вентилятора перед застосуванням ручної швидкості.";
var governorConflict = "Cyan і Oberon активні. Зупиніть один у режимі робочого столу.";
var governorMissing = "Увімкніть Cyan або Oberon у режимі робочого столу.";
var gpuAction = "Оновіть статус GPU та перевірте активний регулятор у режимі настільного комп’ютера.";
var gpuBusyCause = "GPU не перебуває в стані очікування, необхідному для цієї зміни Oberon.";
var gpuBusyGuidance = "Зачекайте, доки GPU повернеться до 1000 МГц, а потім повторіть спробу.";
var gpuCause = "Активний регулятор або поточний стан апаратного забезпечення не підтвердив запитану зміну.";
var gpuDbusAction = "У режимі настільного комп’ютера залиште один регулятор активним і зачекайте, доки D-Bus покаже Підключено.";
var gpuDbusCause = "Cyan зупинено, все ще запускається, неправильно налаштований або конфліктує з Oberon.";
var gpuDbusFailed = "Елементи керування GPU не готові.";
var gpuLive = "Живий GPU";
var gpuOperationFailed = "Не вдалося виконати операцію GPU.";
var gpuRangeAction = "Оновіть і виберіть один із профілів GPU або безпечних точок, які зараз відображаються.";
var gpuRangeCause = "Запитана точка знаходиться за межами безпечної таблиці, про яку повідомляє активний губернатор.";
var gpuRangeFailed = "Вибраний діапазон GPU зараз не підтримується.";
var gpuVoltage = "Напруга";
var helperAction = "Повторно встановіть BC250 Control Center із робочого режиму та відновіть Quick Access.";
var helperCause = "Помічник відсутній, має неправильне право власності або може бути змінений іншим користувачем.";
var helperFailed = "Захищений помічник BC250 відсутній або небезпечний.";
var hide = "Приховати деталі";
var install = "Установити службу";
var installExactProfile = "Буде встановлено лише точний профіль, застосований і перевірений під час цього завантаження.";
var keep = "Тримайте ціль";
var likelyCause = "Ймовірна причина";
var liveRoutingUnchanged = "Живий маршрут не зміниться.";
var loadingCpu = "Читання помічника CPU та телеметрії…";
var loadingTopology = "Читання топології WGP…";
var manualApplyWarning = "Він тимчасово застосовуватиметься на частоті, перевіреній детектором. Перевірте температуру та стабільність перед встановленням служби.";
var memory = "ПАМ'ЯТЬ";
var more = "Більше частот";
var next = "Наступний крок";
var oberonBusy = "Зачекайте, поки GPU повернеться до 1000 МГц";
var oberonIdle = "Зміни тільки в режимі холостого ходу";
var oberonReady = "Готовий до змін";
var pending = "в очікуванні";
var profileBalanced = "Збалансований";
var profileBenchmark = "Тест продуктивності";
var profileGaming = "Ігровий";
var profileRecovery = "Відновлення";
var protocolAction = "Відновіть швидкий доступ у режимі робочого столу, а потім перезапустіть Decky Loader.";
var protocolCause = "Лише частина BC250 Control Center була оновлена, або Decky продовжував працювати старіший процес плагіна.";
var protocolFailed = "Швидкий доступ і його помічник є різними версіями.";
var readOnly = "лише читання";
var remove = "Видалити службу";
var restore = "Відновити поточний стан";
var retryGuidance = "Зачекайте кілька секунд і повторіть спробу.";
var runAutomaticFirst = "Спочатку запустіть автоматичне масштабування";
var safeCuMinimum = "Швидкий доступ зберігає мінімум 24 CU.";
var safeRange = "перевірений діапазон";
var save = "Зберегти вибір";
var serviceRemovedBootProfile = "Сервіс видалено; виявлений профіль залишається доступним під час цього завантаження.";
var snapshotWarning = "Не вдалося оновити спільний знімок CU. Оновіть перед внесенням іншої зміни CU.";
var speed = "Швидкість PWM";
var stale = "Дані застарілі";
var stressMissing = "Відсутня залежність від стресу, необхідна bc250-detect.";
var success = "Зміна перевірена";
var target = "Ціль CU";
var timeoutAction = "Перед повторною спробою перевірте режим робочого столу на предмет запущеного процесу чи помилки служби.";
var timeoutCause = "Помічник, служба, апаратне зчитування або зовнішній інструментарій перестали відповідати.";
var timeoutFailed = "Операція перевищила безпечний ліміт часу.";
var topologyUnavailable = "Топологія WGP недоступна.";
var ttmLimit = "Ліміт TTM";
var unavailable = "недоступний";
var unknownCause = "Швидкий доступ отримав помилку, яка ще не відповідає відомому компоненту.";
var voltageHint = "справжній вхід bc250-detect";
var zram = "ZRAM";
var zswap = "ZSWAP";
var uk = {
	advanced: advanced,
	apply: apply,
	applyChanges: applyChanges,
	automatic: automatic,
	automaticApplyWarning: automaticApplyWarning,
	backingSwap: backingSwap,
	busyAction: busyAction,
	busyCause: busyCause,
	busyFailed: busyFailed,
	channel: channel,
	close: close,
	compute: compute,
	cpuApplyAuto: cpuApplyAuto,
	cpuApplyManual: cpuApplyManual,
	cpuApplying: cpuApplying,
	cpuCause: cpuCause,
	cpuDetectHelp: cpuDetectHelp,
	cpuDetected: cpuDetected,
	cpuFrequency: cpuFrequency,
	cpuGuidance: cpuGuidance,
	cpuHelperUnavailable: cpuHelperUnavailable,
	cpuLiveClock: cpuLiveClock,
	cpuManual: cpuManual,
	cpuManualHelp: cpuManualHelp,
	cpuNeedsDetection: cpuNeedsDetection,
	cpuOperationFailed: cpuOperationFailed,
	cpuPleaseWait: cpuPleaseWait,
	cpuScale: cpuScale,
	cpuStatusUnavailable: cpuStatusUnavailable,
	cpuTarget: cpuTarget,
	cpuTrial: cpuTrial,
	cpuVerifyAction: cpuVerifyAction,
	cpuVerifyCause: cpuVerifyCause,
	cpuVerifyFailed: cpuVerifyFailed,
	cpuVidCeiling: cpuVidCeiling,
	cpuVoltage: cpuVoltage,
	cuBackendAction: cuBackendAction,
	cuBackendCause: cuBackendCause,
	cuBackendFailed: cuBackendFailed,
	cuCause: cuCause,
	cuGuidance: cuGuidance,
	cuOperationFailed: cuOperationFailed,
	current: current,
	details: details,
	detected: detected,
	diagnosticCode: diagnosticCode,
	disabled: disabled,
	elapsed: elapsed,
	enabled: enabled,
	error: error,
	estimated: estimated,
	external: external,
	fan: fan,
	fanCause: fanCause,
	fanGuidance: fanGuidance,
	fanOperationFailed: fanOperationFailed,
	fanRpmObserved: fanRpmObserved,
	fanUnverified: fanUnverified,
	fanWiring: fanWiring,
	governorConflict: governorConflict,
	governorMissing: governorMissing,
	gpuAction: gpuAction,
	gpuBusyCause: gpuBusyCause,
	gpuBusyGuidance: gpuBusyGuidance,
	gpuCause: gpuCause,
	gpuDbusAction: gpuDbusAction,
	gpuDbusCause: gpuDbusCause,
	gpuDbusFailed: gpuDbusFailed,
	gpuLive: gpuLive,
	gpuOperationFailed: gpuOperationFailed,
	gpuRangeAction: gpuRangeAction,
	gpuRangeCause: gpuRangeCause,
	gpuRangeFailed: gpuRangeFailed,
	gpuVoltage: gpuVoltage,
	helperAction: helperAction,
	helperCause: helperCause,
	helperFailed: helperFailed,
	hide: hide,
	install: install,
	installExactProfile: installExactProfile,
	keep: keep,
	likelyCause: likelyCause,
	liveRoutingUnchanged: liveRoutingUnchanged,
	loadingCpu: loadingCpu,
	loadingTopology: loadingTopology,
	manualApplyWarning: manualApplyWarning,
	memory: memory,
	more: more,
	next: next,
	oberonBusy: oberonBusy,
	oberonIdle: oberonIdle,
	oberonReady: oberonReady,
	pending: pending,
	profileBalanced: profileBalanced,
	profileBenchmark: profileBenchmark,
	profileGaming: profileGaming,
	profileRecovery: profileRecovery,
	protocolAction: protocolAction,
	protocolCause: protocolCause,
	protocolFailed: protocolFailed,
	readOnly: readOnly,
	remove: remove,
	restore: restore,
	retryGuidance: retryGuidance,
	runAutomaticFirst: runAutomaticFirst,
	safeCuMinimum: safeCuMinimum,
	safeRange: safeRange,
	save: save,
	serviceRemovedBootProfile: serviceRemovedBootProfile,
	snapshotWarning: snapshotWarning,
	speed: speed,
	stale: stale,
	stressMissing: stressMissing,
	success: success,
	target: target,
	timeoutAction: timeoutAction,
	timeoutCause: timeoutCause,
	timeoutFailed: timeoutFailed,
	topologyUnavailable: topologyUnavailable,
	ttmLimit: ttmLimit,
	unavailable: unavailable,
	unknownCause: unknownCause,
	voltageHint: voltageHint,
	zram: zram,
	zswap: zswap
};

const catalogs = {
    en, es, "es-419": es419, pt, ru, pl, de, uk,
};
function normalizeQuickAccessLanguage(value) {
    const raw = String(value ?? "").trim().toLowerCase().replaceAll("_", "-").split(".", 1)[0];
    const aliases = {
        english: "en", spanish: "es", latam: "es", "spanish-latam": "es",
        portuguese: "pt", brazilian: "pt", "brazilian-portuguese": "pt",
        russian: "ru", polish: "pl", german: "de", ukrainian: "uk",
    };
    const exact = aliases[raw] ?? raw;
    const supported = new Set(["en", "es", "es-419", "pt", "ru", "pl", "de", "uk"]);
    if (supported.has(exact))
        return exact;
    const base = String(exact).split("-", 1)[0];
    return base === "es" || base === "pt" || base === "ru" || base === "pl" || base === "de" || base === "uk" ? base : "en";
}
function detectedLanguage() {
    const steam = globalThis;
    const localeList = steam.LocalizationManager?.m_rgLocalesToUse;
    if (Array.isArray(localeList) && localeList.length)
        return localeList[0];
    const steamLanguage = steam.SteamClient?.Settings?.GetCurrentLanguage?.();
    if (typeof steamLanguage === "string")
        return steamLanguage;
    return globalThis.navigator?.language ?? "en";
}
const quickAccessLanguage = normalizeQuickAccessLanguage(detectedLanguage());
const text = catalogs[quickAccessLanguage];

const getStatus = callable("status");
const getCpuTelemetry = callable("cpu_telemetry");
const applyGpuProfile = callable("apply_gpu_profile");
const applyGpuSafePoint = callable("apply_gpu_safe_point");
const applyCuTable = callable("apply_cu_table");
const saveCuTable = callable("save_cu_table");
const installCuService = callable("install_cu_service");
const removeCuService = callable("remove_cu_service");
const applyFanChannel = callable("apply_fan_channel");
const applyCpuTuning = callable("apply_cpu_tuning");
const applyCpuScale = callable("apply_cpu_scale");
const installCpuService = callable("install_cpu_service");
const removeCpuService = callable("remove_cpu_service");
const fanChannels = [2, 3, 4, 5];
const cuRows = ["SE0.SH0", "SE0.SH1", "SE1.SH0", "SE1.SH1"];
const wordingFor = {
    "BC250-PROTOCOL-001": () => ({ summary: text.protocolFailed, cause: text.protocolCause, action: text.protocolAction }),
    "BC250-HELPER-001": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
    "BC250-BUSY-001": () => ({ summary: text.busyFailed, cause: text.busyCause, action: text.busyAction }),
    "BC250-TIMEOUT-001": () => ({ summary: text.timeoutFailed, cause: text.timeoutCause, action: text.timeoutAction }),
    "BC250-DBUS-001": () => ({ summary: text.gpuDbusFailed, cause: text.gpuDbusCause, action: text.gpuDbusAction }),
    "BC250-RANGE-001": () => ({ summary: text.gpuRangeFailed, cause: text.gpuRangeCause, action: text.gpuRangeAction }),
    "BC250-GPU-001": () => ({ summary: text.gpuOperationFailed, cause: text.gpuCause, action: text.gpuAction }),
    "BC250-CU-001": () => ({ summary: text.cuOperationFailed, cause: text.cuCause, action: text.cuGuidance }),
    "BC250-FAN-001": () => ({ summary: text.fanOperationFailed, cause: text.fanCause, action: text.fanGuidance }),
    "BC250-CPU-001": () => ({ summary: text.cpuOperationFailed, cause: text.cpuCause, action: text.cpuGuidance }),
    "BC250-CPUTOOL-001": () => ({ summary: text.cpuVerifyFailed, cause: text.cpuVerifyCause, action: text.cpuVerifyAction }),
    "BC250-CMD-001": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
    "BC250-CONFIG-001": () => ({ summary: text.gpuOperationFailed, cause: text.gpuCause, action: text.gpuAction }),
    "BC250-SERVICE-003": () => ({ summary: text.gpuOperationFailed, cause: text.gpuCause, action: text.gpuAction }),
    "BC250-HW-001": () => ({ summary: text.error, cause: text.unknownCause, action: text.retryGuidance }),
    "BC250-PERM-001": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
    "BC250-AUTH-002": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
};
const codeByMarker = new Map();
for (const entry of errorCatalog.codes)
    for (const marker of entry.markers)
        codeByMarker.set(marker, entry.code);
function diagnoseError(value) {
    const raw = String(value ?? "");
    let code = "";
    for (const marker of errorCatalog.markers_longest_first) {
        if (raw.includes(marker)) {
            code = codeByMarker.get(marker) ?? "";
            break;
        }
    }
    if (!code) {
        // No marker: the message came from something other than our helpers.
        const lower = raw.toLowerCase();
        if (lower.includes("timed out") || lower.includes("timeout"))
            code = "BC250-TIMEOUT-001";
        else if (lower.includes("protocol") && lower.includes("incompat"))
            code = "BC250-PROTOCOL-001";
        else if (lower.includes("helper") && (lower.includes("missing") || lower.includes("protected") || lower.includes("ownership") || lower.includes("permission")))
            code = "BC250-HELPER-001";
        else if (lower.includes("already") && (lower.includes("running") || lower.includes("operation")))
            code = "BC250-BUSY-001";
        else if (lower.includes("d-bus"))
            code = "BC250-DBUS-001";
        else if (lower.includes("governor"))
            code = "BC250-GPU-001";
        else if (lower.includes("umr") || lower.includes("wgp") || lower.includes("cu table"))
            code = "BC250-CU-001";
        else if (lower.includes("pwm") || lower.includes("nct"))
            code = "BC250-FAN-001";
        else if (lower.includes("bc250-detect") || lower.includes("stress"))
            code = "BC250-CPU-001";
    }
    const wording = wordingFor[code];
    if (!wording)
        return { code: code || "BC250-GENERAL-001", summary: text.error, cause: text.unknownCause, action: text.retryGuidance };
    return { code, ...wording() };
}
const localizedErrorSummary = (value) => diagnoseError(value).summary;
const failed = (error) => ({ ok: false, error: error instanceof Error ? error.message : text.error });
const validMasks = (value) => Array.isArray(value) && value.length === 4 && value.every((mask) => Number.isInteger(mask) && mask >= 0 && mask <= 31);
const countWgps = (masks) => masks.reduce((total, mask) => total + [0, 1, 2, 3, 4].filter((bit) => Boolean(mask & (1 << bit))).length, 0);
const sameMasks = (a, b) => a.length === b.length && a.every((mask, index) => mask === b[index]);
function masksFromTarget(target, targets) {
    const masks = [7, 7, 7, 7];
    // 12 WGPs are always on; the ladder decides how many more there can be.
    const lowest = 24;
    const highest = 40;
    let extra = Math.max(0, Math.min((highest - lowest) / 2, target / 2 - lowest / 2));
    for (let wgp = 3; wgp < 5 && extra > 0; wgp += 1)
        for (let row = 0; row < 4 && extra > 0; row += 1) {
            masks[row] |= 1 << wgp;
            extra -= 1;
        }
    return masks;
}
function PadButton({ children, disabled = false, onActivate, style, preferredFocus = false, label }) {
    const [focused, setFocused] = SP_REACT.useState(false);
    const locked = SP_REACT.useRef(false);
    const activate = () => {
        if (disabled || locked.current)
            return;
        locked.current = true;
        onActivate();
        globalThis.setTimeout(() => { locked.current = false; }, 180);
    };
    return (SP_JSX.jsx(DFL.Button, { "aria-label": label, disabled: disabled, focusable: !disabled, onClick: activate, onOKButton: activate, preferredFocus: preferredFocus, onGamepadFocus: () => setFocused(true), onGamepadBlur: () => setFocused(false), style: {
            background: tokens.colors.panel_raised,
            borderRadius: 6,
            boxSizing: "border-box",
            color: tokens.colors.text,
            outline: "none",
            transition: "border-color 90ms ease",
            ...style,
            opacity: disabled ? .38 : (style?.opacity ?? 1),
            border: focused ? `1px solid ${tokens.colors.focus}` : (style?.border ?? `1px solid ${tokens.colors.border}`),
            boxShadow: focused ? `inset 0 0 0 1px ${tokens.colors.focus_soft}` : "none",
        }, children: children }));
}
function SectionTitle({ kind, title, trailing }) {
    const data = {
        gpu: [SP_JSX.jsx(FaMicrochip, {}), tokens.colors.purple, tokens.colors.purple_soft],
        cu: [SP_JSX.jsx(FaTh, {}), tokens.colors.orange, tokens.colors.orange_soft],
        cpu: [SP_JSX.jsx(FaBolt, {}), tokens.colors.blue, tokens.colors.blue_soft],
        fan: [SP_JSX.jsx(FaFan, {}), tokens.colors.cyan, tokens.colors.cyan_soft],
    }[kind];
    return SP_JSX.jsxs("div", { style: { alignItems: "center", display: "flex", gap: 6, margin: "0 2px 6px" }, children: [SP_JSX.jsx("span", { style: { alignItems: "center", background: data[2], borderRadius: 4, color: data[1], display: "flex", fontSize: 10, height: 16, justifyContent: "center", width: 16 }, children: data[0] }), SP_JSX.jsx("span", { style: { color: tokens.colors.subtle, flex: 1, fontSize: 10, fontWeight: 650, letterSpacing: ".05em" }, children: title }), trailing] });
}
function Notice({ value, dismiss }) {
    const [open, setOpen] = SP_REACT.useState(false);
    const diagnosis = diagnoseError(value);
    return SP_JSX.jsxs("div", { role: "alert", style: { background: tokens.colors.red_soft, border: `1px solid ${tokens.colors.red}`, borderRadius: 8, marginBottom: 10, padding: 9 }, children: [SP_JSX.jsxs("div", { style: { display: "flex", gap: 7 }, children: [SP_JSX.jsx(FaExclamationTriangle, { color: tokens.colors.red }), SP_JSX.jsxs("div", { children: [SP_JSX.jsx("b", { children: text.error }), SP_JSX.jsx("div", { style: { color: tokens.colors.red, fontSize: 11, marginTop: 3 }, children: diagnosis.summary }), SP_JSX.jsxs("div", { style: { color: tokens.colors.muted, fontSize: 10, marginTop: 4 }, children: [SP_JSX.jsxs("b", { children: [text.likelyCause, ":"] }), " ", diagnosis.cause] }), SP_JSX.jsxs("div", { style: { color: tokens.colors.muted, fontSize: 10, marginTop: 4 }, children: [SP_JSX.jsxs("b", { children: [text.next, ":"] }), " ", diagnosis.action] })] })] }), SP_JSX.jsxs("div", { style: { display: "flex", gap: 6, marginTop: 7 }, children: [SP_JSX.jsx(PadButton, { onActivate: () => setOpen(!open), style: { fontSize: 10, minHeight: 30, padding: "4px 8px" }, children: open ? text.hide : text.details }), SP_JSX.jsx(PadButton, { onActivate: dismiss, style: { fontSize: 10, minHeight: 30, padding: "4px 8px" }, children: text.close })] }), open ? SP_JSX.jsxs("pre", { style: { background: tokens.colors.console_bg, color: tokens.colors.red, fontSize: 9, margin: "7px 0 0", overflowWrap: "anywhere", padding: 6, whiteSpace: "pre-wrap" }, children: [text.diagnosticCode, ": ", diagnosis.code, "\n", value] }) : null] });
}
function Action({ label, disabled, primary, danger, onActivate }) {
    return SP_JSX.jsx(PadButton, { disabled: disabled, onActivate: onActivate, style: {
            background: danger ? tokens.colors.red_soft : primary ? tokens.colors.orange : tokens.colors.panel_raised,
            border: `1px solid ${danger ? tokens.colors.red_soft : primary ? tokens.colors.orange : tokens.colors.border}`,
            color: danger ? tokens.colors.red : primary ? tokens.colors.selection : tokens.colors.text,
            alignItems: "center", boxSizing: "border-box", display: "flex", flex: 1, fontSize: 10, fontWeight: primary ? 700 : 600, height: 36, justifyContent: "center", lineHeight: 1.15, minWidth: 0, padding: "4px 7px", textAlign: "center", whiteSpace: "normal", width: "100%",
        }, children: label });
}
function ActionRow({ children, marginBottom = 0 }) {
    return SP_JSX.jsx(DFL.Focusable, { "flow-children": "right", style: { alignItems: "stretch", display: "flex", gap: 6, height: 36, marginBottom, minHeight: 36, width: "100%" }, children: children });
}
function CompactSlider({ label, value, suffix, min, max, step, disabled, onChange }) {
    return SP_JSX.jsxs("div", { style: { background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, marginBottom: 6, padding: "7px 8px 3px" }, children: [SP_JSX.jsxs("div", { style: { alignItems: "baseline", display: "flex", justifyContent: "space-between", marginBottom: 1 }, children: [SP_JSX.jsx("span", { style: { color: tokens.colors.subtle, fontSize: 10 }, children: label }), SP_JSX.jsxs("b", { style: { color: tokens.colors.text, fontSize: 12 }, children: [value, suffix] })] }), SP_JSX.jsx(DFL.SliderField, { label: "", layout: "below", childrenContainerWidth: "max", bottomSeparator: "none", highlightOnFocus: true, value: value, min: min, max: max, step: step, minimumDpadGranularity: step, validValues: "steps", showValue: false, disabled: disabled, onChange: onChange })] });
}
function CpuMetric({ label, value }) {
    return SP_JSX.jsxs("div", { style: { minWidth: 0, padding: "7px 8px" }, children: [SP_JSX.jsx("div", { style: { color: tokens.colors.subtle, fontSize: 8 }, children: label }), SP_JSX.jsx("div", { style: { fontSize: 12, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, children: value })] });
}
function estimateCpuVid(frequency, scale, model) {
    if (!model)
        return null;
    if (frequency < model.floor_mhz)
        return null;
    const p = model.p_base + scale * model.p_scale;
    const q = model.q_base + scale * model.q_scale;
    return Math.round(model.square * frequency * frequency + p * frequency + q);
}
function CuMatrix({ live, driver, draft, disabled, change, minimum }) {
    const active = countWgps(draft);
    const cells = cuRows.flatMap((rowName, row) => [0, 1, 2, 3, 4].map((wgp) => {
        const selected = Boolean(draft[row] & (1 << wgp));
        const routed = Boolean(live[row] & (1 << wgp));
        const inDriver = Boolean(driver[row] & (1 << wgp));
        const pending = selected !== routed;
        const token = selected ? inDriver ? "D+" : "S+" : inDriver ? "D!" : "—";
        const color = pending ? tokens.colors.amber : selected ? inDriver ? tokens.colors.green : tokens.colors.cyan : inDriver ? tokens.colors.red : tokens.colors.disabled_text;
        const background = pending ? tokens.colors.amber_soft : selected ? inDriver ? tokens.colors.green_soft : tokens.colors.cyan_soft : inDriver ? tokens.colors.red_soft : tokens.colors.panel_raised;
        return SP_JSX.jsxs(PadButton, { label: `${rowName} WGP ${wgp} ${token}`, disabled: disabled, preferredFocus: row === 0 && wgp === 0, onActivate: () => { if (selected && active <= 12) {
                minimum();
                return;
            } const next = draft.slice(); next[row] = selected ? next[row] & ~(1 << wgp) : next[row] | (1 << wgp); change(next); }, style: { alignItems: "center", background, border: `1px solid ${pending ? tokens.colors.amber : tokens.colors.border}`, color, display: "flex", flexDirection: "column", fontSize: 9, fontWeight: 700, height: 30, justifyContent: "center", lineHeight: 1, minWidth: 0, padding: 0, width: "100%" }, children: [SP_JSX.jsxs("span", { style: { color: tokens.colors.muted, fontSize: 8, opacity: .72 }, children: [row, ".", wgp] }), SP_JSX.jsx("span", { style: { color, marginTop: 2 }, children: token })] }, `${rowName}-${wgp}`);
    }));
    return SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(DFL.Focusable, { "flow-children": "grid", navEntryPreferPosition: DFL.NavEntryPositionPreferences.PREFERRED_CHILD, style: { background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 8, boxSizing: "border-box", display: "grid", gap: 4, gridTemplateColumns: "repeat(5,minmax(0,1fr))", padding: 7, width: "100%" }, children: cells }), SP_JSX.jsx("div", { style: { color: tokens.colors.muted, display: "flex", fontSize: 10, gap: 8, margin: "6px 0" }, children: [[tokens.colors.green, "D+"], [tokens.colors.cyan, "S+"], [tokens.colors.amber, text.pending], [tokens.colors.red, "D!"]].map(([color, label]) => SP_JSX.jsxs("span", { style: { alignItems: "center", display: "flex", gap: 3 }, children: [SP_JSX.jsx("i", { style: { background: color, borderRadius: 2, height: 7, width: 7 } }), label] }, label)) })] });
}
function Content() {
    const [state, setState] = SP_REACT.useState({});
    const [loaded, setLoaded] = SP_REACT.useState(false);
    const [busy, setBusy] = SP_REACT.useState(false);
    const [stale, setStale] = SP_REACT.useState(false);
    const [feedback, setFeedback] = SP_REACT.useState(null);
    const [highOpen, setHighOpen] = SP_REACT.useState(true);
    const [highSelection, setHighSelection] = SP_REACT.useState(0);
    const [cuDraft, setCuDraft] = SP_REACT.useState(masksFromTarget(24));
    const [cuConflict, setCuConflict] = SP_REACT.useState(false);
    const [fanOpen, setFanOpen] = SP_REACT.useState(false);
    const [fanChannel, setFanChannel] = SP_REACT.useState(2);
    const [fanDuty, setFanDuty] = SP_REACT.useState(50);
    const [cpuFrequency, setCpuFrequency] = SP_REACT.useState(3100);
    const [cpuVid, setCpuVid] = SP_REACT.useState(1150);
    const [cpuScale, setCpuScale] = SP_REACT.useState(-30);
    const [cpuManual, setCpuManual] = SP_REACT.useState(false);
    const [cpuError, setCpuError] = SP_REACT.useState(null);
    const [cpuOperation, setCpuOperation] = SP_REACT.useState(null);
    const [cpuElapsed, setCpuElapsed] = SP_REACT.useState(0);
    const busyRef = SP_REACT.useRef(false);
    const refreshing = SP_REACT.useRef(false);
    const cpuTelemetryRefreshing = SP_REACT.useRef(false);
    const dirty = SP_REACT.useRef({ cu: false, fan: false, gpu: false, cpu: false });
    const selectionRef = SP_REACT.useRef({ fan: 2 });
    SP_REACT.useEffect(() => { selectionRef.current.fan = fanChannel; }, [fanChannel]);
    const refresh = SP_REACT.useCallback(async (reason = "initial") => {
        if (refreshing.current || (reason === "poll" && busyRef.current))
            return;
        refreshing.current = true;
        try {
            const result = await getStatus();
            if (result.ok === false) {
                setLoaded(true);
                setStale(true);
                if (reason === "initial")
                    setFeedback(result.error ?? text.error);
                return;
            }
            setState(result);
            setLoaded(true);
            setStale(false);
            if (validMasks(result.cu_masks))
                setCuDraft((existing) => { if (dirty.current.cu && reason !== "after") {
                    if (!sameMasks(existing, result.cu_masks))
                        setCuConflict(true);
                    return existing;
                } dirty.current.cu = false; setCuConflict(false); return result.cu_masks.slice(); });
            const points = result.gpu_safe_point_ceilings ?? [];
            if (!dirty.current.gpu || reason === "after") {
                // A high point is orange only after Cyan has verified it as the live
                // range. Do not preselect the first TOML point while Benchmark (or
                // another <=2000 MHz profile) is active: that made a controller focus
                // ring look like a second selected frequency.
                const liveHigh = result.gpu_range?.[0] === 1000 && (result.gpu_range?.[1] ?? 0) > 2000
                    ? result.gpu_range[1]
                    : 0;
                setHighSelection(points.some((point) => point.frequency === liveHigh) ? liveHigh : 0);
                dirty.current.gpu = false;
            }
            // Bounds from the payload, never from a copy kept here. Clamping a
            // saved profile against the wrong floor is not a display problem: the
            // clamped value is what the panel then re-applies, so a Desktop profile
            // saved at 3200 MHz used to come back as an unrequested 3500.
            const cpuLimits = result.contract?.cpu;
            const lowFreq = cpuLimits?.frequency_range?.[0] ?? 3100;
            const highFreq = cpuLimits?.frequency_range?.[1] ?? 4200;
            const freqStep = cpuLimits?.frequency_step ?? 50;
            const lowVid = cpuLimits?.vid_range?.[0] ?? 950;
            const highVid = cpuLimits?.vid_range?.[1] ?? 1325;
            const lowScale = cpuLimits?.scale_range?.[0] ?? -50;
            const highScale = cpuLimits?.scale_range?.[1] ?? 0;
            const lowFan = result.contract?.fan?.percent_range?.[0] ?? 20;
            const highFan = result.contract?.fan?.percent_range?.[1] ?? 100;
            const fan = result.fan_channel_options?.find((option) => option.channel === selectionRef.current.fan);
            const duty = fan?.percent;
            if (duty != null && (!dirty.current.fan || reason === "after")) {
                setFanDuty(Math.max(lowFan, Math.min(highFan, duty)));
                dirty.current.fan = false;
            }
            if (!dirty.current.cpu && result.cpu_detected_profile?.ready) {
                const active = result.cpu_active_profile ?? result.cpu_detected_profile.active_profile;
                const selectedFrequency = active?.mode === "manual" ? active.frequency : result.cpu_detected_profile.requested_frequency;
                setCpuFrequency(Math.max(lowFreq, Math.min(highFreq, selectedFrequency)));
                setCpuVid(Math.max(lowVid, Math.min(highVid, result.cpu_detected_profile.requested_vid)));
                setCpuScale(Math.max(lowScale, Math.min(highScale, active?.scale ?? result.cpu_detected_profile.scale)));
                setCpuManual(active?.mode === "manual");
            }
            else if (!dirty.current.cpu && result.cpu_saved_profile) {
                setCpuFrequency(Math.max(lowFreq, Math.min(highFreq, Math.round(result.cpu_saved_profile.frequency / freqStep) * freqStep)));
                setCpuScale(Math.max(lowScale, Math.min(highScale, result.cpu_saved_profile.scale)));
            }
        }
        catch (error) {
            if (reason === "initial")
                setLoaded(true);
            setStale(true);
            if (reason === "initial")
                setFeedback(failed(error).error ?? text.error);
        }
        finally {
            refreshing.current = false;
        }
    }, []);
    SP_REACT.useEffect(() => { void refresh("initial"); const timer = globalThis.setInterval(() => void refresh("poll"), 5000); return () => globalThis.clearInterval(timer); }, [refresh]);
    const sampleCpuTelemetry = SP_REACT.useCallback(async () => {
        if (cpuTelemetryRefreshing.current)
            return;
        cpuTelemetryRefreshing.current = true;
        try {
            const result = await getCpuTelemetry();
            if (result.ok !== false)
                setState((current) => ({
                    ...current,
                    ...(typeof result.cpu_frequency_mhz === "number" ? { cpu_frequency_mhz: result.cpu_frequency_mhz } : {}),
                    ...(typeof result.cpu_temperature_c === "number" ? { cpu_temperature_c: result.cpu_temperature_c } : {}),
                    ...(typeof result.cpu_tuning_ready === "boolean" ? { cpu_tuning_ready: result.cpu_tuning_ready } : {}),
                    ...(typeof result.cpu_tuning_temperature === "number" ? { cpu_tuning_temperature: result.cpu_tuning_temperature } : {}),
                    ...(typeof result.observed_at === "number" ? { observed_at: result.observed_at } : {}),
                }));
        }
        catch {
            // A missed read-only sample is passive: the next sample retries and an
            // explicit OC result remains the authoritative success/failure signal.
        }
        finally {
            cpuTelemetryRefreshing.current = false;
        }
    }, []);
    SP_REACT.useEffect(() => {
        if (!cpuOperation)
            setCpuElapsed(0);
        const tick = () => {
            if (cpuOperation)
                setCpuElapsed(Math.max(0, Math.floor((Date.now() - cpuOperation.startedAt) / 1000)));
        };
        void sampleCpuTelemetry();
        if (cpuOperation)
            tick();
        const telemetryTimer = globalThis.setInterval(() => void sampleCpuTelemetry(), cpuOperation ? 1000 : 3000);
        const elapsedTimer = cpuOperation ? globalThis.setInterval(tick, 1000) : undefined;
        return () => { globalThis.clearInterval(telemetryTimer); if (elapsedTimer !== undefined)
            globalThis.clearInterval(elapsedTimer); };
    }, [cpuOperation, sampleCpuTelemetry]);
    const execute = async (title, operation, kind = "none", cpuProgress) => {
        if (busyRef.current)
            return;
        busyRef.current = true;
        setBusy(true);
        if (kind === "cpu")
            setCpuError(null);
        if (cpuProgress)
            setCpuOperation({ ...cpuProgress, startedAt: Date.now() });
        try {
            const result = await operation();
            if (result.ok === false) {
                const message = result.error ?? text.error;
                if (kind === "cpu")
                    setCpuError(message);
                setFeedback(message);
                toaster.toast({ title, body: localizedErrorSummary(message) });
            }
            else {
                setState((current) => ({ ...current, ...result }));
                if (kind === "gpu" && Array.isArray(result.gpu_range) && result.gpu_range[0] === 1000 && result.gpu_range[1] > 2000)
                    setHighSelection(result.gpu_range[1]);
                else if (kind === "gpu")
                    setHighSelection(0);
                setFeedback(null);
                if (kind !== "none")
                    dirty.current[kind] = false;
                toaster.toast({ title, body: text.success });
                if (kind !== "gpu")
                    await refresh("after");
            }
        }
        catch (error) {
            const result = failed(error);
            const message = result.error ?? text.error;
            if (kind === "cpu")
                setCpuError(message);
            setFeedback(message);
            toaster.toast({ title, body: localizedErrorSummary(message) });
        }
        finally {
            void sampleCpuTelemetry();
            busyRef.current = false;
            setBusy(false);
            setCpuOperation(null);
        }
    };
    const topology = validMasks(state.cu_masks);
    const liveMasks = SP_REACT.useMemo(() => topology ? state.cu_masks.slice() : [0, 0, 0, 0], [topology, state.cu_masks]);
    const driverMasks = SP_REACT.useMemo(() => validMasks(state.cu_driver_masks) ? state.cu_driver_masks.slice() : [0, 0, 0, 0], [state.cu_driver_masks]);
    const draftCUs = countWgps(cuDraft) * 2;
    const detectedFans = state.fan_channel_options?.filter((option) => option.available).map((option) => option.channel) ?? state.system_fan_channels ?? [];
    const fanDetected = detectedFans.includes(fanChannel);
    const liveFan = state.fan_channel_options?.find((option) => option.channel === fanChannel);
    const points = state.gpu_safe_point_ceilings ?? [];
    const liveHighPoint = points.find((point) => point.frequency === highSelection);
    const gpuReady = Boolean(state.gpu_governor_active ?? state.cyan_active);
    const governorName = state.gpu_governor === "oberon" ? "Oberon" : state.gpu_governor === "cyan" ? "Cyan" : "";
    const activeGpuProfiles = state.gpu_profiles ?? [];
    const cpuReady = Boolean(state.cpu_tuning_ready);
    const cpuLimit = state.cpu_tuning_temperature ?? 90;
    const detectedCpu = state.cpu_detected_profile;
    const activeCpu = state.cpu_active_profile ?? detectedCpu?.active_profile;
    const manualReady = Boolean(detectedCpu?.ready && detectedCpu.same_boot && (state.cpu_manual_scale_ready ?? detectedCpu.manual_scale_ready));
    const manualFrequencyReady = Boolean(manualReady && detectedCpu?.frequency === cpuFrequency);
    const detectedCpuSummary = detectedCpu
        ? detectedCpu.requested_frequency === detectedCpu.frequency
            ? `${detectedCpu.frequency} MHz · scale ${detectedCpu.scale}`
            : `${text.cpuTarget} ${detectedCpu.requested_frequency} → ${detectedCpu.frequency} MHz · scale ${detectedCpu.scale}`
        : "";
    const manualScaleDescription = !manualReady
        ? text.runAutomaticFirst
        : manualFrequencyReady
            ? text.cpuManualHelp
            : `${text.cpuManualHelp} · ${detectedCpu?.frequency ?? "—"} MHz`;
    // Every bound the controls below use comes from the helper with the state.
    // The panel used to declare its own, and its CPU floor was 3500 against a
    // real 3100 — so 3100-3450 MHz was unreachable in Game Mode, and a profile
    // saved at 3200 on the Desktop was rounded up before being re-applied.
    const limits = state.contract;
    const cpuBounds = limits?.cpu;
    const cpuMin = cpuBounds?.frequency_range?.[0] ?? 3100;
    const cpuMax = cpuBounds?.frequency_range?.[1] ?? 4200;
    const cpuStep = cpuBounds?.frequency_step ?? 50;
    const vidMin = cpuBounds?.vid_range?.[0] ?? 950;
    const vidMax = cpuBounds?.vid_range?.[1] ?? 1325;
    const vidStep = cpuBounds?.vid_step ?? 5;
    const scaleMin = cpuBounds?.scale_range?.[0] ?? -50;
    const scaleMax = cpuBounds?.scale_range?.[1] ?? 0;
    const fanMin = limits?.fan?.percent_range?.[0] ?? 20;
    const fanMax = limits?.fan?.percent_range?.[1] ?? 100;
    const fanStep = limits?.fan?.percent_step ?? 5;
    const selectedEstimatedVid = estimateCpuVid(cpuFrequency, cpuScale, cpuBounds?.vid_model);
    const activeMatchesTarget = cpuManual
        ? Boolean(activeCpu?.persistable && activeCpu.mode === "manual" && activeCpu.frequency === cpuFrequency && activeCpu.scale === cpuScale)
        : Boolean(activeCpu?.persistable && activeCpu.mode === "automatic" && detectedCpu?.requested_frequency === cpuFrequency && detectedCpu.requested_vid === cpuVid);
    const confirmCpu = (mode) => DFL.showModal(SP_JSX.jsx(DFL.ConfirmModal, { strTitle: mode === "detect" ? (cpuManual ? text.cpuApplyManual : text.cpuApplyAuto) : text.install, strDescription: mode === "detect"
            ? cpuManual
                ? `${cpuFrequency} MHz · ${text.cpuScale} ${cpuScale} · VID ${text.estimated} ${selectedEstimatedVid} mV · ${cpuLimit}°C. ${text.manualApplyWarning}`
                : `${cpuFrequency} MHz · ${text.cpuVoltage} ${cpuVid} mV · ${cpuLimit}°C. ${text.automaticApplyWarning}`
            : `${activeCpu?.frequency ?? "—"} MHz · ${text.cpuScale} ${activeCpu?.scale ?? "—"} · ${activeCpu?.estimated_vid ?? "—"} mV ${text.estimated} · ${activeCpu?.temperature ?? cpuLimit}°C. ${text.installExactProfile}`, strOKButtonText: mode === "detect" ? (cpuManual ? text.cpuApplyManual : text.cpuApplyAuto) : text.install, onOK: () => void execute("BC250 CPU", mode === "detect" ? (cpuManual ? () => applyCpuScale(cpuFrequency, cpuScale) : () => applyCpuTuning(cpuFrequency, cpuVid)) : installCpuService, "cpu", mode === "detect" ? { target: cpuFrequency, manual: cpuManual } : undefined) }));
    return SP_JSX.jsxs(DFL.Focusable, { "flow-children": "down", style: { background: tokens.colors.panel, border: `1px solid ${tokens.colors.border}`, borderRadius: 12, boxSizing: "border-box", color: tokens.colors.text, padding: "12px 14px 72px", width: "100%" }, children: [stale ? SP_JSX.jsxs("div", { style: { alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, display: "flex", fontSize: 10, gap: 6, marginBottom: 10, padding: "6px 9px" }, children: [SP_JSX.jsx(FaClock, {}), text.stale] }) : null, feedback ? SP_JSX.jsx(Notice, { value: feedback, dismiss: () => setFeedback(null) }) : null, SP_JSX.jsxs("section", { style: { marginBottom: 12 }, children: [SP_JSX.jsx(SectionTitle, { kind: "gpu", title: "GPU", trailing: governorName ? SP_JSX.jsx("span", { style: { color: tokens.colors.subtle, fontSize: 9 }, children: governorName }) : undefined }), !gpuReady && loaded ? SP_JSX.jsx("div", { style: { color: state.gpu_governor === "conflict" ? tokens.colors.red : tokens.colors.amber, fontSize: 9, marginBottom: 6 }, children: state.gpu_governor === "conflict" ? text.governorConflict : text.governorMissing }) : null, SP_JSX.jsxs(DFL.Focusable, { "flow-children": "grid", navEntryPreferPosition: DFL.NavEntryPositionPreferences.PREFERRED_CHILD, style: { display: "grid", gap: 6, gridTemplateColumns: "1fr 1fr", marginBottom: 6 }, children: [SP_JSX.jsxs("div", { style: { background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, boxSizing: "border-box", display: "flex", flexDirection: "column", height: 48, justifyContent: "center", padding: "5px 9px", width: "100%" }, children: [SP_JSX.jsx("span", { style: { color: tokens.colors.subtle, fontSize: 9, fontWeight: 650 }, children: text.gpuLive }), SP_JSX.jsxs("b", { style: { color: tokens.colors.text, fontSize: 12, lineHeight: 1.25 }, children: [state.gpu_core_mhz ?? "—", " MHz"] }), SP_JSX.jsxs("span", { style: { color: tokens.colors.subtle, fontSize: 9 }, children: [text.gpuVoltage, " \u00B7 ", state.gpu_voltage_mv ?? "—", " mV"] })] }), activeGpuProfiles.map((profile) => { const current = state.gpu_range?.[0] === profile.min && state.gpu_range?.[1] === profile.max && (state.gpu_governor !== "cyan" || state.gpu_performance_enabled === false); const allowed = Boolean(state.gpu_allowed_range && state.gpu_allowed_range[0] <= profile.min && profile.max <= state.gpu_allowed_range[1]); return SP_JSX.jsxs(PadButton, { disabled: busy || !gpuReady || !allowed, preferredFocus: profile.key === (state.gpu_governor === "oberon" ? "oberon-1850" : "balanced"), onActivate: () => { void execute(`GPU · ${profile.name}`, () => applyGpuProfile(profile.key), "gpu"); }, style: { alignItems: "flex-start", background: current ? tokens.colors.orange_soft : tokens.colors.panel_raised, border: `1px solid ${current ? tokens.colors.orange : tokens.colors.border}`, display: "flex", flexDirection: "column", height: 48, justifyContent: "center", padding: "6px 9px", textAlign: "left", width: "100%" }, children: [SP_JSX.jsx("span", { style: { color: current ? tokens.colors.orange : tokens.colors.text, fontSize: 12, fontWeight: 650 }, children: profile.name }), SP_JSX.jsxs("span", { style: { color: current ? tokens.colors.orange : tokens.colors.subtle, fontSize: 10 }, children: [profile.min, "\u2013", profile.max, " MHz", current ? ` · ${text.current}` : ""] })] }, profile.key); })] }), points.length ? SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsxs(PadButton, { onActivate: () => setHighOpen(!highOpen), disabled: busy || !gpuReady, style: { alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }, children: [SP_JSX.jsx("span", { children: text.more }), SP_JSX.jsx("span", { style: { color: tokens.colors.orange }, children: highOpen ? "▴" : "▾" })] }), highOpen ? SP_JSX.jsx(DFL.Focusable, { "flow-children": "grid", navEntryPreferPosition: DFL.NavEntryPositionPreferences.PREFERRED_CHILD, style: { background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr", padding: 6 }, children: points.map((point, index) => { const current = point.frequency === liveHighPoint?.frequency; const allowed = Boolean(state.gpu_allowed_range && point.frequency <= state.gpu_allowed_range[1]); return SP_JSX.jsxs(PadButton, { disabled: busy || !gpuReady || !allowed, preferredFocus: current || (!liveHighPoint && index === 0), onActivate: () => { if (!current)
                                        void execute(`GPU · ${governorName || text.advanced}`, () => applyGpuSafePoint(point.frequency), "gpu"); }, style: { background: current ? tokens.colors.orange_soft : tokens.colors.panel_alt, border: `1px solid ${current ? tokens.colors.orange : tokens.colors.border}`, color: current ? tokens.colors.orange : tokens.colors.text, fontSize: 10, height: 34, padding: 4, textAlign: "center", width: "100%" }, children: [point.frequency, " MHz \u00B7 ", point.voltage, " mV", current ? ` · ${text.current}` : ""] }, point.frequency); }) }) : null] }) : null] }), SP_JSX.jsxs("section", { style: { marginBottom: 12 }, children: [SP_JSX.jsx(SectionTitle, { kind: "cu", title: text.compute, trailing: SP_JSX.jsxs("b", { style: { color: tokens.colors.orange, fontSize: 11 }, children: [draftCUs, "/40 ", text.target] }) }), state.cu_snapshot_warning ? SP_JSX.jsx("div", { style: { color: tokens.colors.amber, fontSize: 10, marginBottom: 6 }, children: text.snapshotWarning }) : null, cuConflict ? SP_JSX.jsxs("div", { style: { background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, fontSize: 10, marginBottom: 6, padding: 6 }, children: [text.external, SP_JSX.jsx("div", { style: { marginTop: 5 }, children: SP_JSX.jsxs(ActionRow, { children: [SP_JSX.jsx(Action, { label: text.restore, disabled: busy, onActivate: () => { dirty.current.cu = false; setCuConflict(false); setCuDraft(liveMasks); } }), SP_JSX.jsx(Action, { label: text.keep, disabled: busy, onActivate: () => setCuConflict(false) })] }) })] }) : null, topology ? SP_JSX.jsx(CuMatrix, { live: liveMasks, driver: driverMasks, draft: cuDraft, disabled: busy || !state.cu_backend_ready, change: (masks) => { dirty.current.cu = true; setCuConflict(false); setCuDraft(masks); }, minimum: () => setFeedback(text.safeCuMinimum) }) : SP_JSX.jsx("div", { style: { color: loaded ? tokens.colors.amber : tokens.colors.subtle, fontSize: 10, marginBottom: 6 }, children: loaded ? text.topologyUnavailable : text.loadingTopology }), SP_JSX.jsxs("div", { style: { minHeight: 78, width: "100%" }, children: [SP_JSX.jsxs(ActionRow, { marginBottom: 6, children: [SP_JSX.jsx(Action, { label: text.applyChanges, primary: true, disabled: busy || !topology || !state.cu_backend_ready || sameMasks(cuDraft, liveMasks), onActivate: () => void execute("BC250 CU", () => applyCuTable(cuDraft), "cu") }), SP_JSX.jsx(Action, { label: text.save, disabled: busy || !topology || !state.cu_backend_ready, onActivate: () => void execute("BC250 CU", () => saveCuTable(cuDraft), "cu") })] }), SP_JSX.jsxs(ActionRow, { children: [SP_JSX.jsx(Action, { label: text.install, disabled: busy || Boolean(state.cu_service_installed) || !validMasks(state.cu_saved_masks ?? undefined), onActivate: () => void execute("BC250 CU", installCuService, "cu") }), SP_JSX.jsx(Action, { label: text.remove, danger: true, disabled: busy || !state.cu_service_installed, onActivate: () => DFL.showModal(SP_JSX.jsx(DFL.ConfirmModal, { strTitle: text.remove, strDescription: text.liveRoutingUnchanged, strOKButtonText: text.remove, bDestructiveWarning: true, onOK: () => void execute("BC250 CU", removeCuService, "cu") })) })] })] })] }), SP_JSX.jsxs("section", { style: { marginBottom: 12 }, children: [SP_JSX.jsx(SectionTitle, { kind: "cpu", title: "CPU" }), cpuError ? SP_JSX.jsx("div", { style: { background: tokens.colors.red_soft, border: `1px solid ${tokens.colors.red}`, borderRadius: 6, color: tokens.colors.red, fontSize: 9, lineHeight: 1.35, marginBottom: 7, overflowWrap: "anywhere", padding: "6px 8px" }, children: localizedErrorSummary(cpuError) }) : null, cpuOperation ? SP_JSX.jsxs("div", { role: "status", "aria-live": "polite", style: { background: tokens.colors.blue_soft, border: `1px solid ${tokens.colors.blue}`, borderRadius: 7, marginBottom: 7, padding: "8px 9px" }, children: [SP_JSX.jsxs("div", { style: { alignItems: "center", display: "flex", gap: 7 }, children: [SP_JSX.jsx("span", { style: { background: tokens.colors.blue, borderRadius: "50%", boxShadow: `0 0 0 3px ${tokens.colors.blue_soft}`, height: 7, width: 7 } }), SP_JSX.jsx("b", { style: { color: tokens.colors.blue, flex: 1, fontSize: 11 }, children: text.cpuApplying }), SP_JSX.jsxs("span", { style: { color: tokens.colors.subtle, fontSize: 9 }, children: [text.elapsed, ": ", cpuElapsed, "s"] })] }), SP_JSX.jsx("div", { style: { color: tokens.colors.subtle, fontSize: 9, margin: "4px 0 7px 14px" }, children: text.cpuPleaseWait }), SP_JSX.jsxs("div", { style: { display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr" }, children: [SP_JSX.jsxs("div", { style: { background: tokens.colors.panel_alt, borderRadius: 5, padding: "5px 7px" }, children: [SP_JSX.jsx("span", { style: { color: tokens.colors.muted, display: "block", fontSize: 8 }, children: text.cpuLiveClock }), SP_JSX.jsxs("b", { style: { fontSize: 12 }, children: [state.cpu_frequency_mhz ?? "—", " MHz"] })] }), SP_JSX.jsxs("div", { style: { background: tokens.colors.panel_alt, borderRadius: 5, padding: "5px 7px" }, children: [SP_JSX.jsx("span", { style: { color: tokens.colors.muted, display: "block", fontSize: 8 }, children: text.cpuTarget }), SP_JSX.jsxs("b", { style: { fontSize: 12 }, children: [cpuOperation.target, " MHz"] })] })] })] }) : null, SP_JSX.jsxs("div", { style: { background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gridTemplateColumns: "1fr 1fr", marginBottom: 6, overflow: "hidden" }, children: [SP_JSX.jsx(CpuMetric, { label: "CLOCK", value: `${state.cpu_frequency_mhz ?? "—"} MHz` }), SP_JSX.jsx("div", { style: { borderLeft: `1px solid ${tokens.colors.border}` }, children: SP_JSX.jsx(CpuMetric, { label: "TCTL", value: `${state.cpu_temperature_c?.toFixed(1) ?? "—"} °C` }) }), SP_JSX.jsx("div", { style: { borderTop: `1px solid ${tokens.colors.border}` }, children: SP_JSX.jsx(CpuMetric, { label: "VID EST.", value: activeCpu ? `${activeCpu.estimated_vid} mV` : "—" }) }), SP_JSX.jsx("div", { style: { borderLeft: `1px solid ${tokens.colors.border}`, borderTop: `1px solid ${tokens.colors.border}` }, children: SP_JSX.jsx(CpuMetric, { label: "SCALE", value: activeCpu ? String(activeCpu.scale) : "—" }) })] }), detectedCpu?.ready ? SP_JSX.jsxs("div", { style: { alignItems: "center", background: tokens.colors.green_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }, children: [SP_JSX.jsx("span", { style: { color: tokens.colors.subtle }, children: text.cpuDetected }), SP_JSX.jsx("b", { style: { color: tokens.colors.green }, children: detectedCpuSummary })] }) : null, SP_JSX.jsx("div", { style: { color: !loaded || cpuReady || state.cpu_tuning_source === "detector-required" ? tokens.colors.subtle : tokens.colors.red, fontSize: 9, margin: "0 2px 7px" }, children: !loaded ? text.loadingCpu : cpuReady ? `${text.cpuTrial}: ${cpuLimit}°C · ${text.cpuDetectHelp}` : (state.cpu_tuning_source === "stress-unavailable" ? text.stressMissing : (state.cpu_tuning_source === "detector-required" ? text.cpuNeedsDetection : (state.cpu_tuning_source === "helper-unavailable" ? text.cpuHelperUnavailable : text.cpuStatusUnavailable))) }), loaded && !cpuReady && state.cpu_tuning_error && state.cpu_tuning_source !== "detector-required" ? SP_JSX.jsx("div", { style: { color: tokens.colors.muted, fontSize: 8, margin: "-3px 2px 7px", overflowWrap: "anywhere" }, children: localizedErrorSummary(state.cpu_tuning_error) }) : null, SP_JSX.jsxs("div", { style: { borderTop: `1px solid ${tokens.colors.border_soft}`, paddingTop: 7 }, children: [SP_JSX.jsx(CompactSlider, { label: text.cpuFrequency, value: cpuFrequency, suffix: " MHz", min: cpuMin, max: cpuMax, step: cpuStep, disabled: busy || !cpuReady, onChange: (value) => { setCpuFrequency(Math.max(cpuMin, Math.min(cpuMax, Math.round(value / cpuStep) * cpuStep))); dirty.current.cpu = true; } }), SP_JSX.jsx(CompactSlider, { label: text.cpuVoltage, value: cpuVid, suffix: " mV", min: vidMin, max: vidMax, step: vidStep, disabled: busy || !cpuReady || cpuManual, onChange: (value) => { setCpuVid(Math.max(vidMin, Math.min(vidMax, Math.round(value / 5) * 5))); dirty.current.cpu = true; } }), !cpuManual && cpuVid >= vidMax - 25 ? SP_JSX.jsx("div", { style: { color: tokens.colors.amber, fontSize: 8, lineHeight: 1.3, margin: "-2px 2px 7px" }, children: text.cpuVidCeiling }) : null, SP_JSX.jsx("div", { style: { background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, marginBottom: 6, overflow: "hidden" }, children: SP_JSX.jsx(DFL.ToggleField, { label: text.cpuManual, description: manualScaleDescription, layout: "inline", bottomSeparator: "none", highlightOnFocus: true, checked: cpuManual, disabled: busy || !manualReady, onChange: (checked) => { setCpuManual(checked); if (checked && detectedCpu) {
                                        setCpuScale(activeCpu?.frequency === detectedCpu.frequency ? (activeCpu.scale ?? detectedCpu.scale) : detectedCpu.scale);
                                    } dirty.current.cpu = true; } }) }), cpuManual && detectedCpu && !manualFrequencyReady ? SP_JSX.jsxs("div", { style: { color: tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "-2px 2px 7px" }, children: [text.cpuManualHelp, " \u00B7 ", detectedCpu.frequency, " MHz"] }) : null, SP_JSX.jsx(CompactSlider, { label: text.cpuScale, value: cpuScale, suffix: "", min: scaleMin, max: scaleMax, step: 1, disabled: busy || !cpuManual || !manualFrequencyReady, onChange: (value) => { setCpuScale(Math.max(-50, Math.min(0, Math.round(value)))); dirty.current.cpu = true; } }), SP_JSX.jsxs("div", { style: { color: tokens.colors.disabled_text, display: "flex", fontSize: 9, justifyContent: "space-between", margin: "0 2px 7px" }, children: [SP_JSX.jsx("span", { children: cpuManual ? `${text.cpuScale}: ${scaleMin}…${scaleMax}` : `${text.voltageHint} · ${vidMin}–${vidMax} mV` }), SP_JSX.jsx("span", { children: cpuManual ? `~${selectedEstimatedVid ?? "—"} mV` : `${text.safeRange}: ${cpuMin}–${cpuMax} MHz` })] }), SP_JSX.jsx(ActionRow, { children: SP_JSX.jsx(Action, { label: cpuManual ? text.cpuApplyManual : text.cpuApplyAuto, primary: true, disabled: busy || !cpuReady || (cpuManual && (!manualFrequencyReady || (selectedEstimatedVid ?? 0) > vidMax)), onActivate: () => confirmCpu("detect") }) })] }), SP_JSX.jsx("div", { style: { marginTop: 6, minHeight: 36 }, children: SP_JSX.jsxs(ActionRow, { children: [SP_JSX.jsx(Action, { label: text.install, disabled: busy || !activeMatchesTarget || Boolean(state.cpu_service_enabled), onActivate: () => confirmCpu("install") }), SP_JSX.jsx(Action, { label: text.remove, danger: true, disabled: busy || (!state.cpu_service_installed && !state.cpu_service_enabled), onActivate: () => DFL.showModal(SP_JSX.jsx(DFL.ConfirmModal, { strTitle: text.remove, strDescription: text.serviceRemovedBootProfile, strOKButtonText: text.remove, bDestructiveWarning: true, onOK: () => void execute("BC250 CPU", removeCpuService, "cpu") })) })] }) })] }), SP_JSX.jsxs("section", { style: { marginBottom: 12 }, children: [SP_JSX.jsx(SectionTitle, { kind: "fan", title: text.fan }), SP_JSX.jsxs(PadButton, { disabled: busy, onActivate: () => setFanOpen(!fanOpen), style: { alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }, children: [SP_JSX.jsxs("span", { children: [liveFan?.label ?? `PWM ${fanChannel}`, " \u00B7 ", fanDetected ? text.detected : text.unavailable] }), SP_JSX.jsx("span", { style: { color: tokens.colors.cyan }, children: fanOpen ? "▴" : "▾" })] }), fanOpen ? SP_JSX.jsx(DFL.Focusable, { "flow-children": "grid", navEntryPreferPosition: DFL.NavEntryPositionPreferences.PREFERRED_CHILD, style: { display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr", marginBottom: 7 }, children: fanChannels.map((channel) => { const option = state.fan_channel_options?.find((item) => item.channel === channel); const available = detectedFans.includes(channel); return SP_JSX.jsxs(PadButton, { disabled: busy || !available, preferredFocus: channel === fanChannel, onActivate: () => { selectionRef.current.fan = channel; setFanChannel(channel); setFanOpen(false); dirty.current.fan = false; const percent = option?.percent; if (percent != null)
                                setFanDuty(percent); }, style: { background: channel === fanChannel ? tokens.colors.cyan_soft : tokens.colors.panel_raised, border: `1px solid ${channel === fanChannel ? tokens.colors.cyan : tokens.colors.border}`, color: channel === fanChannel ? tokens.colors.cyan : tokens.colors.text, fontSize: 10, height: 34, padding: 4, width: "100%" }, children: ["PWM ", channel, " \u00B7 ", available ? `${option?.percent ?? "—"}%` : text.unavailable] }, channel); }) }) : null, liveFan ? SP_JSX.jsx("div", { style: { color: liveFan.rpm_observed ? tokens.colors.subtle : tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "0 2px 6px" }, children: liveFan.rpm_observed ? `${text.fanRpmObserved}: ${liveFan.rpm} RPM` : `${text.fanUnverified}. ${fanChannel === 2 ? text.fanWiring : ""}` }) : null, SP_JSX.jsx(DFL.SliderField, { label: text.speed, value: fanDuty, min: fanMin, max: fanMax, step: fanStep, minimumDpadGranularity: fanStep, showValue: true, valueSuffix: "%", disabled: busy || !fanDetected, onChange: (value) => { dirty.current.fan = true; setFanDuty(Math.max(20, Math.min(100, Math.round(value / 5) * 5))); } }), SP_JSX.jsxs(DFL.Focusable, { "flow-children": "grid", style: { display: "grid", gap: 6, gridTemplateColumns: "1fr 1fr", marginTop: 6 }, children: [SP_JSX.jsx(Action, { label: text.apply, primary: true, disabled: busy || !fanDetected, onActivate: () => void execute(`PWM ${fanChannel}`, () => applyFanChannel(fanChannel, fanDuty), "fan") }), SP_JSX.jsx(Action, { label: text.automatic, disabled: busy || !fanDetected, onActivate: () => void execute(`PWM ${fanChannel}`, () => applyFanChannel(fanChannel, "automatic"), "fan") })] })] })] });
}
var index = definePlugin(() => ({
    name: "BC250 Quick Access",
    titleView: SP_JSX.jsx("div", { className: DFL.staticClasses.Title, children: "BC250 Quick Access" }),
    content: SP_JSX.jsx(Content, {}),
    icon: SP_JSX.jsx(FaMicrochip, {}),
    onDismount() { },
}));

export { index as default };
//# sourceMappingURL=index.js.map
