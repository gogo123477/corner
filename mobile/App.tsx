import { StatusBar } from "expo-status-bar";
import React from "react";
import { SafeAreaView, StyleSheet } from "react-native";
import { MorningBriefScreen } from "./src/screens/MorningBriefScreen";

export default function App() {
  return (
    <SafeAreaView style={styles.root}>
      <MorningBriefScreen />
      <StatusBar style="auto" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
