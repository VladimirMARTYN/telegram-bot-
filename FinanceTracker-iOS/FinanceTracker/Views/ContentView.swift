//
//  ContentView.swift
//  FinanceTracker
//
//  Main content view with tab navigation
//

import SwiftUI

struct ContentView: View {
    @StateObject private var dataManager = DataManager.shared
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView()
                .tabItem {
                    Label("Главная", systemImage: "house.fill")
                }
                .tag(0)
            
            TransactionListView()
                .tabItem {
                    Label("Транзакции", systemImage: "list.bullet")
                }
                .tag(1)
            
            StatisticsView()
                .tabItem {
                    Label("Статистика", systemImage: "chart.bar.fill")
                }
                .tag(2)
            
            BudgetView()
                .tabItem {
                    Label("Бюджет", systemImage: "creditcard.fill")
                }
                .tag(3)
            
            SettingsView()
                .tabItem {
                    Label("Настройки", systemImage: "gearshape.fill")
                }
                .tag(4)
        }
        .environmentObject(dataManager)
    }
}

struct CurrencyFormatter {
    static func format(_ amount: Double, currency: String = "RUB") -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: amount)) ?? "\(amount)"
    }
}




