import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "community.codex-usage"

  readonly property string scriptPath: String(Qt.resolvedUrl("usage.py")).replace(/^(?:file|qs):\/\//, "")
  property var usage: ({ available: false, remaining: null })
  readonly property var grok: usage.grok || ({ available: false, remaining: null })
  property bool popupOpen: false

  function close() { popupOpen = false }
  function refresh() {
    if (!usageProcess.running) usageProcess.running = true
  }
  function scheduleClose() { closeTimer.restart() }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Component.onCompleted: Qt.callLater(refresh)

  Process {
    id: usageProcess
    command: ["python3", root.scriptPath, "--quickshell"]
    stderr: StdioCollector {
      onStreamFinished: if (text.trim()) console.warn("Codex usage:", text.trim())
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          root.usage = JSON.parse(String(text || "{}"))
        } catch (_error) {
          root.usage = ({ available: false, remaining: null })
        }
      }
    }
  }

  Timer {
    interval: 180000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Timer {
    id: closeTimer
    interval: 180
    onTriggered: if (!button.tooltipHovered && !popup.containsMouse) root.popupOpen = false
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    labelVisible: false
    hasVisualContent: true
    implicitWidth: barLabels.implicitWidth + scaledHorizontalMargin * 2
    tooltipText: ""

    Row {
      id: barLabels
      anchors.centerIn: parent
      spacing: Style.space(12)

      ProviderLabel {
        icon: "assets/codex.svg"
        usageState: root.usage
      }
      ProviderLabel {
        icon: "assets/grok.svg"
        usageState: root.grok
      }
    }

    onTooltipHoveredChanged: {
      if (tooltipHovered) {
        closeTimer.stop()
        root.popupOpen = true
        root.refresh()
      } else {
        root.scheduleClose()
      }
    }
    onPressed: function(button) {
      if (button === Qt.RightButton) root.refresh()
      else if (button === Qt.LeftButton) Quickshell.execDetached(["xdg-open", "https://chatgpt.com/codex"])
    }
  }

  component ProviderLabel: Row {
    required property string icon
    required property var usageState
    spacing: Style.space(5)

    Image {
      width: Style.space(14)
      height: width
      anchors.verticalCenter: parent.verticalCenter
      source: Qt.resolvedUrl(parent.icon)
      sourceSize.width: width * 2
      sourceSize.height: height * 2
      fillMode: Image.PreserveAspectFit
      layer.enabled: true
      layer.effect: MultiEffect {
        colorization: 1
        colorizationColor: root.bar.foreground
      }
    }
    Text {
      text: parent.usageState.available ? parent.usageState.remaining + "%" : "--"
      color: parent.usageState.available && parent.usageState.remaining <= 30
        ? Color.urgent : root.bar.foreground
      font.family: root.bar.fontFamily
      font.pixelSize: button.fontSize
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  component PaceGraph: Row {
    id: paceGraph
    required property var usageState
    property string periodLabel: "7D"
    width: parent.width
    spacing: Style.space(12)

    Column {
      width: Style.space(116)
      spacing: Style.space(2)

      Row {
        spacing: Style.space(10)
        Text {
          text: paceGraph.periodLabel
          color: Qt.darker(root.bar.foreground, 1.35)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        Text {
          text: paceGraph.usageState.available ? paceGraph.usageState.status : "Unavailable"
          color: paceGraph.usageState.pace_state === "behind" ? Color.urgent : Color.accent
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
      }

      Row {
        spacing: Style.space(2)
        Text {
          text: paceGraph.usageState.available ? paceGraph.usageState.glyph : "—"
          color: paceGraph.usageState.pace_state === "behind" ? Color.urgent : Color.accent
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.title
          font.bold: true
        }
        Text {
          text: paceGraph.usageState.available ? paceGraph.usageState.margin : "—"
          color: paceGraph.usageState.pace_state === "behind" ? Color.urgent : Color.accent
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.display
          font.bold: true
        }
        Text {
          text: "%"
          color: Qt.darker(root.bar.foreground, 1.35)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.body
          anchors.bottom: parent.bottom
          anchors.bottomMargin: Style.space(4)
        }
      }
    }

    Canvas {
      id: chart
      width: parent.width - Style.space(128)
      height: Style.space(62)
      antialiasing: true

      onWidthChanged: requestPaint()
      onHeightChanged: requestPaint()
      Connections {
        target: paceGraph
        function onUsageStateChanged() { chart.requestPaint() }
      }

      onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        if (!paceGraph.usageState.available) return

        var left = 1, top = 4, right = width - 1, bottom = height - 2
        var plotWidth = right - left, plotHeight = bottom - top
        var elapsed = Math.max(0.001, Math.min(0.999, Number(paceGraph.usageState.elapsed)))
        var nowX = left + plotWidth * elapsed
        var actualY = top + plotHeight * Number(paceGraph.usageState.used) / 100
        var accent = paceGraph.usageState.pace_state === "behind" ? Color.urgent : Color.accent
        var segments = paceGraph.usageState.segments || []
        var slot = plotWidth / 7
        var referenceHeight = plotHeight * 0.46

        for (var i = 0; i < 7; i++) {
          var segment = segments[i] || [1, 1, null]
          var x = left + i * slot
          if (segment[2] === null) {
            ctx.fillStyle = Qt.rgba(root.bar.foreground.r, root.bar.foreground.g, root.bar.foreground.b, 0.06)
            ctx.fillRect(x, bottom - referenceHeight, slot - 1, referenceHeight)
            continue
          }
          var barWidth = Number(segment[0]) * (slot - 1)
          var totalHeight = Number(segment[1]) * referenceHeight
          ctx.fillStyle = Qt.rgba(root.bar.foreground.r, root.bar.foreground.g, root.bar.foreground.b, Number(segment[2]))
          ctx.fillRect(x, bottom - totalHeight, barWidth, totalHeight)
        }

        ctx.lineWidth = 1
        ctx.strokeStyle = Qt.rgba(root.bar.foreground.r, root.bar.foreground.g, root.bar.foreground.b, 0.25)
        ctx.setLineDash([2.5, 3])
        ctx.beginPath()
        ctx.moveTo(left, top)
        ctx.lineTo(right, bottom)
        ctx.stroke()

        if (paceGraph.usageState.show_projection) {
          ctx.strokeStyle = accent
          ctx.setLineDash([1, 4])
          ctx.beginPath()
          ctx.moveTo(nowX, actualY)
          ctx.lineTo(left + plotWidth * Number(paceGraph.usageState.projection_elapsed), top + plotHeight * Number(paceGraph.usageState.projected) / 100)
          ctx.stroke()
        }

        ctx.strokeStyle = accent
        ctx.lineWidth = 2.4
        ctx.setLineDash([])
        ctx.beginPath()
        ctx.moveTo(left, top)
        ctx.lineTo(nowX, actualY)
        ctx.stroke()
        ctx.fillStyle = accent
        ctx.beginPath()
        ctx.arc(nowX, actualY, 3.3, 0, Math.PI * 2)
        ctx.fill()
      }
    }
  }


  PopupCard {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.popupOpen
    triggerMode: "hover"
    contentWidth: popup.fittedContentWidth(Style.space(340))
    contentHeight: popup.fittedContentHeight(content.implicitHeight)

    onContainsMouseChanged: {
      if (containsMouse) closeTimer.stop()
      else root.scheduleClose()
    }

    Column {
      id: content
      anchors.fill: parent
      spacing: Style.space(10)

      Row {
        width: parent.width
        spacing: Style.space(7)

        Text {
          text: "●"
          color: Color.accent
          font.pixelSize: Style.font.caption
          anchors.verticalCenter: parent.verticalCenter
        }
        Text {
          text: "Codex"
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.subtitle
          font.bold: true
          anchors.verticalCenter: parent.verticalCenter
        }
        Text {
          text: "SESSION & WEEKLY"
          color: Qt.darker(root.bar.foreground, 1.45)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          horizontalAlignment: Text.AlignRight
          width: parent.width - Style.space(92)
          anchors.verticalCenter: parent.verticalCenter
        }
      }

      Row {
        spacing: Style.space(12)
        Text {
          text: "5H"
          color: Qt.darker(root.bar.foreground, 1.35)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        Text {
          text: root.usage.available && root.usage.session_used !== null
            ? root.usage.session_used + "% used" : "No session data"
          color: Qt.darker(root.bar.foreground, 1.35)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      PanelSeparator { foreground: root.bar.foreground }

      PaceGraph { usageState: root.usage }

      Text {
        text: root.usage.available ? "↻  " + root.usage.reset : "Right-click to retry"
        color: Qt.darker(root.bar.foreground, 1.35)
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.caption
      }

      PanelSeparator { foreground: root.bar.foreground }

      Row {
        width: parent.width
        spacing: Style.space(7)
        Text {
          id: grokDot
          text: "●"
          color: Color.accent
          font.pixelSize: Style.font.caption
          anchors.verticalCenter: parent.verticalCenter
        }
        Text {
          text: "Grok"
          width: parent.width / 2 - grokDot.implicitWidth - parent.spacing * 2
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.subtitle
          font.bold: true
        }
        Text {
          text: root.grok.available ? root.grok.remaining + "% left" : "Unavailable"
          width: parent.width / 2
          horizontalAlignment: Text.AlignRight
          color: root.grok.available && root.grok.remaining <= 30 ? Color.urgent : Color.accent
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.body
        }
      }

      Text {
        text: "Cursor shared billing cycle"
        color: Qt.darker(root.bar.foreground, 1.35)
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.caption
      }

      PaceGraph {
        usageState: root.grok
        periodLabel: "CYCLE"
      }

      Text {
        text: root.grok.available ? "↻  " + root.grok.reset : "Sign in to Cursor and right-click to retry"
        color: Qt.darker(root.bar.foreground, 1.35)
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }
}
