import SwiftUI

// MARK: - Liquid Glass Optical Surface & Refraction Modifier

public struct LiquidGlassModifier: ViewModifier {
    var cornerRadius: CGFloat
    var isInteractive: Bool
    var isHighlighted: Bool

    public init(cornerRadius: CGFloat = 10, isInteractive: Bool = false, isHighlighted: Bool = false) {
        self.cornerRadius = cornerRadius
        self.isInteractive = isInteractive
        self.isHighlighted = isHighlighted
    }

    public func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    // 1. Ultra-thin material backdrop
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .fill(.ultraThinMaterial)

                    // 2. Optical refraction sheen (diagonal light caustics)
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .fill(
                            LinearGradient(
                                stops: [
                                    .init(color: .white.opacity(isHighlighted ? 0.18 : 0.08), location: 0.0),
                                    .init(color: .white.opacity(isHighlighted ? 0.06 : 0.02), location: 0.35),
                                    .init(color: .clear, location: 0.65),
                                    .init(color: .white.opacity(0.04), location: 1.0)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )

                    // 3. Specular reflective rim border
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .strokeBorder(
                            LinearGradient(
                                stops: [
                                    .init(color: .white.opacity(isHighlighted ? 0.45 : 0.32), location: 0.0),
                                    .init(color: .white.opacity(isHighlighted ? 0.22 : 0.14), location: 0.4),
                                    .init(color: .white.opacity(0.06), location: 0.75),
                                    .init(color: .black.opacity(0.20), location: 1.0)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: 0.75
                        )
                }
            )
            .shadow(color: .black.opacity(0.08), radius: 6, x: 0, y: 2)
            .shadow(color: .black.opacity(0.04), radius: 1, x: 0, y: 1)
    }
}

public extension View {
    func liquidGlass(cornerRadius: CGFloat = 10, isInteractive: Bool = false, isHighlighted: Bool = false) -> some View {
        self.modifier(LiquidGlassModifier(cornerRadius: cornerRadius, isInteractive: isInteractive, isHighlighted: isHighlighted))
    }
}

// MARK: - Liquid Glass Morphing Dropdown with Shared Active Coordinator

public struct LiquidGlassDropdown<Item: Identifiable & Equatable>: View {
    let id: String
    let items: [Item]
    @Binding var selectedItem: Item
    @Binding var activeDropdownId: String?
    let itemLabel: (Item) -> String
    var width: CGFloat?

    @State private var hoveredItemId: Item.ID? = nil

    private let collapsedHeight: CGFloat = 30
    private var actualWidth: CGFloat { width ?? 140 }

    private var isExpanded: Bool {
        activeDropdownId == id
    }

    public init(
        id: String,
        items: [Item],
        selectedItem: Binding<Item>,
        activeDropdownId: Binding<String?>,
        itemLabel: @escaping (Item) -> String,
        width: CGFloat? = nil
    ) {
        self.id = id
        self.items = items
        self._selectedItem = selectedItem
        self._activeDropdownId = activeDropdownId
        self.itemLabel = itemLabel
        self.width = width
    }

    public var body: some View {
        // Fixed layout anchor: reserves stable space so page layout NEVER shifts
        Color.clear
            .frame(width: actualWidth, height: collapsedHeight)
            .overlay(alignment: .topLeading) {
                morphingContainer
            }
            .zIndex(isExpanded ? 999 : 1)
    }

    @ViewBuilder
    private var morphingContainer: some View {
        ZStack(alignment: .topLeading) {
            // Tahoe Ambient Blur Halo (expands synchronously with the morphing container)
            if isExpanded {
                RoundedRectangle(cornerRadius: 14)
                    .fill(.ultraThinMaterial)
                    .frame(width: actualWidth + 20, height: expandedHeight + 20)
                    .blur(radius: 8)
                    .shadow(color: .black.opacity(0.40), radius: 22, x: 0, y: 10)
                    .offset(x: -10, y: -10)
                    .transition(.opacity)
            }

            // The Physical Morphing Liquid Glass Container
            VStack(alignment: .leading, spacing: 0) {
                // Trigger Button: Clicking toggles activeDropdownId, immediately collapsing any other dropdown
                Button(action: {
                    withAnimation(.spring(response: 0.32, dampingFraction: 0.76)) {
                        if activeDropdownId == id {
                            activeDropdownId = nil
                        } else {
                            activeDropdownId = id
                        }
                    }
                }) {
                    HStack(spacing: 6) {
                        Text(itemLabel(selectedItem))
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.primary)
                            .lineLimit(1)

                        Spacer(minLength: 2)

                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundColor(.secondary)
                            .rotationEffect(.degrees(isExpanded ? 180 : 0))
                    }
                    .padding(.horizontal, 8)
                    .frame(width: actualWidth, height: collapsedHeight)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                // Morphing Content List (Fades in seamlessly as container height animates)
                if isExpanded {
                    Divider()
                        .background(Color.white.opacity(0.12))
                        .padding(.horizontal, 4)

                    ScrollView(.vertical, showsIndicators: items.count > 6) {
                        VStack(alignment: .leading, spacing: 1) {
                            ForEach(items) { item in
                                let isSelected = item == selectedItem
                                let isHovered = hoveredItemId == item.id

                                Button(action: {
                                    withAnimation(.spring(response: 0.28, dampingFraction: 0.80)) {
                                        selectedItem = item
                                        activeDropdownId = nil
                                    }
                                }) {
                                    HStack(spacing: 4) {
                                        if isSelected {
                                            Image(systemName: "checkmark")
                                                .font(.system(size: 8, weight: .bold))
                                                .foregroundColor(.primary)
                                                .frame(width: 10)
                                        } else {
                                            Spacer().frame(width: 10)
                                        }

                                        Text(itemLabel(item))
                                            .font(.system(size: 11, weight: isSelected ? .medium : .regular))
                                            .foregroundColor(isSelected ? .primary : .secondary)
                                            .lineLimit(1)

                                        Spacer(minLength: 0)
                                    }
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 5)
                                    .background(
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(isHovered ? Color.white.opacity(0.12) : (isSelected ? Color.white.opacity(0.06) : Color.clear))
                                    )
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .onHover { hovering in
                                    hoveredItemId = hovering ? item.id : nil
                                }
                            }
                        }
                        .padding(3)
                    }
                    .frame(height: listContentHeight)
                    .transition(.opacity)
                }
            }
            .frame(width: actualWidth)
            .liquidGlass(cornerRadius: 9, isInteractive: true, isHighlighted: isExpanded)
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.76), value: isExpanded)
    }

    private var listContentHeight: CGFloat {
        min(CGFloat(items.count * 26 + 8), 160)
    }

    private var expandedHeight: CGFloat {
        collapsedHeight + (isExpanded ? (listContentHeight + 5) : 0)
    }
}

// MARK: - Liquid Glass Action Button (High Disabled Text Saturation & Crisp Contrast)

public struct LiquidGlassButton: View {
    let title: String
    let icon: String?
    var isLoading: Bool = false
    var isProminent: Bool = false
    var isDisabled: Bool = false
    let action: () -> Void

    @State private var isHovered = false
    @State private var isPressed = false

    public init(
        title: String,
        icon: String? = nil,
        isLoading: Bool = false,
        isProminent: Bool = false,
        isDisabled: Bool = false,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.icon = icon
        self.isLoading = isLoading
        self.isProminent = isProminent
        self.isDisabled = isDisabled
        self.action = action
    }

    public var body: some View {
        Button(action: {
            if !isDisabled && !isLoading {
                action()
            }
        }) {
            HStack(spacing: 6) {
                if isLoading {
                    ProgressView()
                        .controlSize(.small)
                } else if let icon = icon {
                    Image(systemName: icon)
                        .font(.system(size: 11, weight: isProminent ? .semibold : .medium))
                }

                Text(title)
                    .font(.system(size: 11, weight: isProminent ? .semibold : .medium))
            }
            // Requirement 1: Elevated saturation and contrast when disabled (0.60 opacity instead of washed out 0.24)
            .foregroundColor(isDisabled ? Color.primary.opacity(0.60) : .primary)
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(isDisabled || isLoading)
        .liquidGlass(cornerRadius: 8, isInteractive: true, isHighlighted: isHovered)
        // High visibility base opacity for clear readability
        .opacity(isDisabled ? 0.85 : 1.0)
        .scaleEffect(isPressed ? 0.96 : 1.0)
        .animation(.spring(response: 0.25, dampingFraction: 0.7), value: isPressed)
        .onHover { hovering in
            isHovered = hovering && !isDisabled
        }
    }
}
