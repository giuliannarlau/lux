// Timing
window.onload = function() {
    var now = new Date().getTime();
    var page_load_time = now - performance.timing.navigationStart;
    console.log("User-perceived page loading time: " + page_load_time);
  }


/**
 * Sets the current date as the minimum allowable date for a date input field.
 * This function is used in new_project.html and project.html
 * @param {HTMLElement} minDateInput - The input element to set the minimum date for.
 */
function getCurrentDate(minDateInput) {
    let today = new Date();

    // Convert today's date to ISO string format and then to YYYY-MM-DD format
    minExpireDate = today.toISOString().split('T')[0];

    minDateInput.min = minExpireDate;
}


/**
 * Checks if a user's Freighter wallet is connected and displays a modal if it isn't.
 * This function is used in index.html and project.html.
 * @param {HTMLElement} element - The HTML element that triggers this check, typically a button or link.
 * @returns {boolean} - Returns true if the wallet is connected, false otherwise.
 */
function checkUser(element) {

    // Display a modal prompting the user to connect the wallet if there isn't a public key attached to the element.
    if (!element.name) {
        document.getElementById("modalBody").innerHTML = "You need to connect you wallet first!";
        const modal = new bootstrap.Modal(document.getElementById("alertModal"));
        modal.show();
        return false;

    // Redirect to create a new project if user is connected
    } else {
        if (element.id == "startProjectLink") { // Element placed in index.html
            window.location.href = "/new_project";
        }
    }
    return true;
};


/**
 * Fetches the user's public key from the Freighter extension and sends it to the server.
 * It checks for the availability of the Freighter extension and the user's consent to share their public key.
 * If the extension isn't installed or the user doesn't consent to share their key, it alerts the user accordingly.
 * This function is used in layout.html. 
*/
async function fetchKey() {
    event.preventDefault();

    if (await window.freighterApi.isConnected()) {

        // Ensure Freighter API is available
        if (typeof window.freighterApi !== "undefined") {
            try {

                // Get public key and send it to the server
                const publicKey = await window.freighterApi.getPublicKey();
                await sendKey(publicKey);
            } catch (error) {

                // Display an alert if user refuses to share the public key
                alert("You have to share your key to log in");
                throw error;
            }
        } else {
            console.log("Object not defined");
            alert("Freighter ran through some problem, please try again later.");
        }
    }
    else {
        // Display an alert if user doesn't have Freighter extesion installed
        alert("You need to install Freighter extension first. Click on 'Create Wallet'");
    }
};


/**
 * Sends the user's public key to the server via a POST request.
 * Handle the server response to either reload the page on success
 * or log errors and alert the user on extension failure.
 * This function is called by fetchKey.
 * @param {string} publicKey - The public key retrieved from the Freighter extension.
 */
async function sendKey(publicKey) {

    const requestOptions = {
        method: "POST",
        headers: {
            "Content-Type": "multipart/form-data",
        },
        body: publicKey,
    };

    try {

        // Send the public key to the server
        const response = await fetch("/", requestOptions);

        // Reload page if response is successful 
        if (response.ok) {
            location.reload();
        } else {
            console.log("Error: Public key was NOT send.");
        }

    // Deal with issue with the Freighter extension
    } catch (error) {
        console.log("Request error", error);
        alert("Freighter ran through some issue. Please try again later");
    }
};


/**
 * Sets the lock state of the alert modal (layout.html) based on the specified state.
 * When locked, the modal cannot be closed by the user. Unlocking restores the closing functionality.
 * This function is called in project.js and controlPanel.js.
 * @param {string} state - Can be 'lock' or 'unlock', defining whether the modal should be locked or unlocked.
 */
function setModalLockState(state) {

    // Get an existing modal instance or create a new one if none exists
    let modalElement = document.getElementById("alertModal");
    let modal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement);

    if (state == "lock") {

        // Lock closing modal options
        modal._config.backdrop = 'static';
        modal._config.keyboard = false;
        document.querySelector('.btn-close').style.display = 'none';
        document.querySelector('.modal-footer button').style.display = 'none';
        modal.show();
    } else {

        // Unlock closing modal options
        modal._config.backdrop = true;
        modal._config.keyboard = true;
        document.querySelector('.btn-close').style.display = 'block';
        document.querySelector('.modal-footer button').style.display = 'block';
    }
}


/**
 * Signs a transaction using the Freighter browser extension.
 * Retrieves the user's public key and uses it to sign the transaction on Stellar's TESTNET.
 * This function is called by controlPanel.js and project.js.
 * @param {string} transactionXdr - The transaction to be signed in XDR format.
 * @returns {Promise<string>} - A promise that resolves to the signed transaction XDR.
 */
async function signingTransaction(transactionXdr) {
    try {

        // Get public key
        const public_key = window.freighterApi.getPublicKey();
        const publicKeyString = public_key.toString();

        // Use the Freighter API to sign the transaction in the TESTET network
        const signedTransaction = await window.freighterApi.signTransaction(transactionXdr, "TESTNET", publicKeyString);
        return signedTransaction;

    // Show error if signing fails
    } catch (error) {
        throw error;
    }
};


/**
 * Sends a signed transaction to the server for submission to the Stellar network.
 * The server handles the transaction submission and any related errors, responding 
 * with the transaction hash or an error message.
 * This function is called by controlPanel.js and project.js.
 * @param {string} signedTransactionXdr - The signed transaction in XDR format.
 * @returns {Promise<string>} - A promise that resolves to the hash of the submitted transaction.
 */
async function sendTransaction(signedTransactionXdr) {

    const requestOptions = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(signedTransactionXdr)
    };

    try {

        // Send the signed transaction to the server and wait for the response
        let response = await fetch("/send_transaction", requestOptions);
        
        // Return the hash if response is successful
        if (response.ok) {
            let data = await response.json();
            return data.hash;
        }
    } catch (error) {
        throw error;
    }
};