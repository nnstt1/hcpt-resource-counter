package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

type PostRequest struct {
	Name string `json:"name"`
	Age  int    `json:"age"`
}

func httpGetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	name := r.URL.Query().Get("name")
	if name == "" {
		name = "World"
	}

	log.Printf("Processing GET request. Name: %s", name)
	fmt.Fprintf(w, "Hello, %s!", name)
}

func httpPostHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req PostRequest
	decoder := json.NewDecoder(r.Body)
	if err := decoder.Decode(&req); err != nil {
		http.Error(w, "Invalid JSON in request body", http.StatusBadRequest)
		return
	}

	log.Printf("Processing POST request. Name: %s", req.Name)

	if req.Name == "" || req.Age == 0 {
		http.Error(w, "Please provide both 'name' and 'age' in the request body.", http.StatusBadRequest)
		return
	}

	fmt.Fprintf(w, "Hello, %s! You are %d years old!", req.Name, req.Age)
}

func main() {
	listenAddr := ":8080"
	if val, ok := os.LookupEnv("FUNCTIONS_CUSTOMHANDLER_PORT"); ok {
		listenAddr = ":" + val
	}

	http.HandleFunc("/api/httpget", httpGetHandler)
	http.HandleFunc("/api/httppost", httpPostHandler)

	log.Printf("Server starting on %s", listenAddr)
	log.Fatal(http.ListenAndServe(listenAddr, nil))
}
