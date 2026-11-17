using System.Runtime.InteropServices;

namespace WlanAnalyzer.Wlan;

// P/Invoke-Deklarationen fuer die Windows Native WiFi API (wlanapi.dll).
// Die Strukturen werden bewusst NICHT als C#-structs nachgebaut, sondern
// in WlanClient ueber feste Offsets gelesen - siehe dort fuer das Layout
// (alle Angaben fuer 64- und 32-Bit identisch, da die Strukturen keine
// Zeiger enthalten).
internal static class WlanNative
{
    public const uint ErrorSuccess = 0;
    public const uint ErrorAccessDenied = 5;
    public const uint ErrorInvalidState = 5023;

    public const uint NotificationSourceAcm = 0x08;
    public const uint AcmScanComplete = 7;
    public const uint AcmScanFail = 8;

    public const int IntfOpcodeCurrentConnection = 7;
    public const int Dot11BssTypeAny = 3;

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    public delegate void WlanNotificationCallback(IntPtr notificationData, IntPtr context);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanOpenHandle(uint clientVersion, IntPtr reserved,
        out uint negotiatedVersion, out IntPtr clientHandle);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanCloseHandle(IntPtr clientHandle, IntPtr reserved);

    [DllImport("wlanapi.dll")]
    public static extern void WlanFreeMemory(IntPtr memory);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanEnumInterfaces(IntPtr clientHandle, IntPtr reserved,
        out IntPtr interfaceList);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanScan(IntPtr clientHandle, ref Guid interfaceGuid,
        IntPtr dot11Ssid, IntPtr ieData, IntPtr reserved);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanGetNetworkBssList(IntPtr clientHandle, ref Guid interfaceGuid,
        IntPtr dot11Ssid, int bssType, [MarshalAs(UnmanagedType.Bool)] bool securityEnabled,
        IntPtr reserved, out IntPtr bssList);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanGetAvailableNetworkList(IntPtr clientHandle, ref Guid interfaceGuid,
        uint flags, IntPtr reserved, out IntPtr networkList);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanQueryInterface(IntPtr clientHandle, ref Guid interfaceGuid,
        int opCode, IntPtr reserved, out uint dataSize, out IntPtr data, IntPtr opcodeValueType);

    [DllImport("wlanapi.dll")]
    public static extern uint WlanRegisterNotification(IntPtr clientHandle, uint notifSource,
        [MarshalAs(UnmanagedType.Bool)] bool ignoreDuplicate, WlanNotificationCallback? callback,
        IntPtr context, IntPtr reserved, out uint prevNotifSource);
}
