import SwiftUI
import EQCosplayCore

public struct HeadphonePickerView: View {
    @ObservedObject var appState: AppState
    @State private var hoveredSourceId: String? = nil
    @State private var hoveredTargetId: String? = nil

    public init(appState: AppState) {
        self.appState = appState
    }

    public var body: some View {
        HStack(alignment: .top, spacing: 18) {
            // Source Headphone Column
            headphoneColumn(
                id: "source_search",
                title: I18n.shared.t("source_headphone"),
                query: $appState.sourceQuery,
                selected: $appState.selectedSource,
                results: appState.sourceResults,
                hoveredId: $hoveredSourceId,
                onSearch: { appState.searchSource() }
            )

            // Target Headphone Column
            headphoneColumn(
                id: "target_search",
                title: I18n.shared.t("target_headphone"),
                query: $appState.targetQuery,
                selected: $appState.selectedTarget,
                results: appState.targetResults,
                hoveredId: $hoveredTargetId,
                onSearch: { appState.searchTarget() }
            )
        }
    }

    @ViewBuilder
    private func headphoneColumn(
        id: String,
        title: String,
        query: Binding<String>,
        selected: Binding<HeadphoneEntry?>,
        results: [HeadphoneEntry],
        hoveredId: Binding<String?>,
        onSearch: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Section Title
            Text(title)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.secondary)

            // Fixed Layout Anchor (Guarantees no lower views shift)
            GeometryReader { geo in
                let boxWidth = geo.size.width
                let isListOpen = appState.activeDropdownId == id && !results.isEmpty && selected.wrappedValue == nil
                let listHeight = min(CGFloat(results.count * 30 + 10), 180)
                let totalHeight = 32 + (isListOpen ? (listHeight + 6) : 0)

                ZStack(alignment: .topLeading) {
                    // Tahoe Extended Blur Halo (Smoothly morphs with container)
                    if isListOpen {
                        RoundedRectangle(cornerRadius: 14)
                            .fill(.ultraThinMaterial)
                            .frame(width: boxWidth + 20, height: totalHeight + 20)
                            .blur(radius: 8)
                            .shadow(color: .black.opacity(0.40), radius: 24, x: 0, y: 10)
                            .offset(x: -10, y: -10)
                            .transition(.opacity)
                    }

                    // Continuous Morphing Liquid Glass Container (Search bar -> Expanded list)
                    VStack(alignment: .leading, spacing: 0) {
                        // Search bar input row
                        HStack(spacing: 8) {
                            if selected.wrappedValue == nil {
                                Image(systemName: "magnifyingglass")
                                    .foregroundColor(.secondary)
                                    .font(.system(size: 12))
                                    .transition(.asymmetric(
                                        insertion: .opacity.combined(with: .scale(scale: 0.8)),
                                        removal: .opacity.combined(with: .scale(scale: 0.5))
                                    ))
                            }

                            if let s = selected.wrappedValue {
                                HStack(spacing: 6) {
                                    Text("\(s.name) (\(s.provider))")
                                        .font(.system(size: 12, weight: .medium))
                                        .foregroundColor(.primary)
                                        .lineLimit(1)
                                    Spacer()
                                }
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) {
                                        query.wrappedValue = s.name
                                        selected.wrappedValue = nil
                                        onSearch()
                                        appState.activeDropdownId = id
                                    }
                                }
                            } else {
                                TextField("", text: query)
                                    .textFieldStyle(.plain)
                                    .foregroundColor(.primary)
                                    .font(.system(size: 12))
                                    .onChange(of: query.wrappedValue) { _ in
                                        onSearch()
                                        withAnimation(.spring(response: 0.30, dampingFraction: 0.78)) {
                                            if !results.isEmpty || !query.wrappedValue.isEmpty {
                                                appState.activeDropdownId = id
                                            }
                                        }
                                    }
                            }

                            if selected.wrappedValue != nil || !query.wrappedValue.isEmpty {
                                Button(action: {
                                    withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) {
                                        selected.wrappedValue = nil
                                        query.wrappedValue = ""
                                        if appState.activeDropdownId == id {
                                            appState.activeDropdownId = nil
                                        }
                                        onSearch()
                                    }
                                }) {
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.system(size: 12))
                                        .foregroundColor(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, 10)
                        .frame(height: 32)

                        // Morphing List inside the same continuous liquid glass shell
                        if isListOpen {
                            Divider()
                                .background(Color.white.opacity(0.12))
                                .padding(.horizontal, 4)

                            ScrollView {
                                LazyVStack(alignment: .leading, spacing: 2) {
                                    ForEach(results) { entry in
                                        let isHovered = hoveredId.wrappedValue == entry.id

                                        Button(action: {
                                            withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) {
                                                selected.wrappedValue = entry
                                                appState.activeDropdownId = nil
                                            }
                                        }) {
                                            HStack {
                                                Text(entry.name)
                                                    .font(.system(size: 12))
                                                    .foregroundColor(.primary)
                                                    .lineLimit(1)
                                                Spacer()
                                                Text(entry.provider)
                                                    .font(.system(size: 10, design: .monospaced))
                                                    .foregroundColor(.secondary)
                                            }
                                            .padding(.horizontal, 8)
                                            .padding(.vertical, 5)
                                            .background(
                                                RoundedRectangle(cornerRadius: 6)
                                                    .fill(isHovered ? Color.white.opacity(0.12) : Color.clear)
                                            )
                                            .contentShape(Rectangle())
                                        }
                                        .buttonStyle(.plain)
                                        .onHover { hovering in
                                            hoveredId.wrappedValue = hovering ? entry.id : nil
                                        }
                                    }
                                }
                                .padding(4)
                            }
                            .frame(height: listHeight)
                            .transition(.opacity)
                        }
                    }
                    .frame(width: boxWidth)
                    .liquidGlass(cornerRadius: 10, isInteractive: true, isHighlighted: isListOpen)
                }
                .animation(.spring(response: 0.32, dampingFraction: 0.76), value: isListOpen)
                .animation(.spring(response: 0.32, dampingFraction: 0.78), value: selected.wrappedValue != nil)
                .zIndex(isListOpen ? 999 : 1)
            }
            .frame(height: 32)
        }
    }
}
