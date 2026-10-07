# tabs.ps1 -- list / close Windows Terminal tabs, including DEAD ones.
#
# Why this exists: killing a tab's shell process does NOT remove its tab.
# WT's default closeOnExit is "graceful", so a force-killed shell leaves a
# tab showing "process exited" forever. Such a tab has NO process at all,
# so nothing on the process side can see or remove it -- UI Automation is the
# only clean handle. This script does that.
#
# Usage (ASCII-only on purpose: a .ps1 containing Chinese gets read as GBK
# by PowerShell on this machine and fails to parse):
#
#   powershell -NoProfile -File tabs.ps1
#       -> list every WT window and its tabs (index + title)
#
#   powershell -NoProfile -File tabs.ps1 -Close "Deepseek*-B"
#       -> close tabs whose title matches that wildcard (all windows)
#
#   powershell -NoProfile -File tabs.ps1 -Close "Deepseek*-B" -Window 527458
#       -> restrict to one window handle
#
# Matching is a PowerShell wildcard (-like), so keep it ASCII: the * covers
# whatever Chinese characters are in the title.
param(
    [string]$Close = "",
    [long]$Window = 0,
    [switch]$Escape
)

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

# Console is GBK here, so printing a Chinese tab title comes out as mojibake.
# -Escape renders non-ASCII as \uXXXX, which always survives the console.
function Show([string]$s) {
    if (-not $Escape) { return $s }
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $s.ToCharArray()) {
        if ([int]$ch -lt 128) { [void]$sb.Append($ch) }
        else { [void]$sb.Append(('\u{0:x4}' -f [int]$ch)) }
    }
    return $sb.ToString()
}

$TYPE_TAB = [System.Windows.Automation.ControlType]::TabItem
$TYPE_BTN = [System.Windows.Automation.ControlType]::Button

$root = [System.Windows.Automation.AutomationElement]::RootElement
$wcond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ClassNameProperty,
    'CASCADIA_HOSTING_WINDOW_CLASS')
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $wcond)
$tabCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty, $TYPE_TAB)
$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty, $TYPE_BTN)

if ($wins.Count -eq 0) { Write-Output 'No Windows Terminal window found.'; exit 0 }

$hit = 0
for ($i = 0; $i -lt $wins.Count; $i++) {
    $w = $wins.Item($i)
    $h = [long]$w.Current.NativeWindowHandle
    if ($Window -ne 0 -and $h -ne $Window) { continue }
    $tabs = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tabCond)
    Write-Output ("window handle=" + $h + "  tabs=" + $tabs.Count + "  title=" + (Show $w.Current.Name))
    for ($j = 0; $j -lt $tabs.Count; $j++) {
        $t = $tabs.Item($j)
        $name = $t.Current.Name
        if ($Close -eq "") {
            Write-Output ("   [" + $j + "] " + (Show $name))
            continue
        }
        if ($name -like $Close) {
            $btns = $t.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
            if ($btns.Count -gt 0) {
                $btns.Item(0).GetCurrentPattern(
                    [System.Windows.Automation.InvokePattern]::Pattern).Invoke()
                Write-Output ("   closed [" + $j + "] " + (Show $name))
                $hit++
            } else {
                Write-Output ("   MATCH but no close button: [" + $j + "] " + (Show $name))
            }
        }
    }
}
if ($Close -ne "") { Write-Output ("matched/closed: " + $hit) }
