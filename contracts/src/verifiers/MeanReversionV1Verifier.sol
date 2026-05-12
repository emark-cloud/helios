// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MeanReversionV1Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 20491192805390485299153009773594534940189261866228447918068658471970481763042;
    uint256 constant alphay  = 9383485363053290200918347156157836566562967994039712273449902621266178545958;
    uint256 constant betax1  = 4252822878758300859123897981450591353533073413197771768651442665752259397132;
    uint256 constant betax2  = 6375614351688725206403948262868962793625744043794305715222011528459656738731;
    uint256 constant betay1  = 21847035105528745403288232691147584728191162732299865338377159692350059136679;
    uint256 constant betay2  = 10505242626370262277552901082094356697409835680220590971873171140371331206856;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 7111752766313155402403129684365149111888013008469145651032332631160792114407;
    uint256 constant deltax2 = 8283338443784760126158352744514344680443998044773534222017363169725387256669;
    uint256 constant deltay1 = 10223489379483842923958042329466793299679220765613387391896478229829698643396;
    uint256 constant deltay2 = 11456425356917817849238617618420377018164231634656303182429622094915833805539;

    
    uint256 constant IC0x = 16682536519829499043815683943418993151107304877785636862033795251573610954204;
    uint256 constant IC0y = 19972911520986420446590508686935607870942421372714345196449725118929142313460;
    
    uint256 constant IC1x = 20213118166097841270001193182457897355417773306928566466750700859907214724111;
    uint256 constant IC1y = 4170979317180890264508357900543024024465462531500136262121703592370336247628;
    
    uint256 constant IC2x = 12637341198178769832443861374756482027054481228404249544615729617421339326147;
    uint256 constant IC2y = 19677336765515743861688300635073320634593187391526681318397847482209524158952;
    
    uint256 constant IC3x = 19599737345587568234303897280630162711481156894622849352260079080154672414128;
    uint256 constant IC3y = 3209362373809418956725501047470560459615803648954415921478560893223965248578;
    
    uint256 constant IC4x = 21771719453166851433158916952808032044626075289059922682833908145865395918833;
    uint256 constant IC4y = 17081005912209770982884910956653335689329945586481014085563602539126103370319;
    
    uint256 constant IC5x = 18084377648782012858218414288936949246217404831361038963446282333075964659741;
    uint256 constant IC5y = 1506945692315462919689646974293435609399637315773986528870533171197112726047;
    
    uint256 constant IC6x = 18528822351991514765179911212785360419875274656700034870632141082599056870197;
    uint256 constant IC6y = 18569067153914051419252167477713541726226851854046295152049888238064510512857;
    
    uint256 constant IC7x = 1715833112392818937025868680359337274800665070066776832127796679256196186648;
    uint256 constant IC7y = 3392791168470952626827291287626860361455631624902169901504756092112812958965;
    
    uint256 constant IC8x = 21098096542404984516804537321246637386605386270121000003945843532424038561574;
    uint256 constant IC8y = 16474860959726392528217109098427172547753231170616144664652260477251607304505;
    
    uint256 constant IC9x = 14892689186892730546288002406372617547156052705865669269359732324902489348137;
    uint256 constant IC9y = 8911879171916910797123118045709419492420117996151140578014155192670727956294;
    
    uint256 constant IC10x = 4302260112192491172275189087385475650437578582901327091042987312104028405435;
    uint256 constant IC10y = 1430737497135096613440060607812699446693361435574831620692112166829324926419;
    
    uint256 constant IC11x = 6202297241174717605581483219037552857557487732799997560405752970077547407600;
    uint256 constant IC11y = 13905235013985500208158600487171996159601511827999685092011544119815071917222;
    
    uint256 constant IC12x = 2433070063087224016188600121196726838127440731349948063322898538921900166391;
    uint256 constant IC12y = 2492669173583640959748563953790692712630040509452658337595164074860526211673;
    
    uint256 constant IC13x = 7118581281331937810824463067526394890807832698980718803735516233612462768548;
    uint256 constant IC13y = 17336812869500920623727743522896558178226607645020837655345714906375625706712;
    
    uint256 constant IC14x = 19076051596526933990776117653904854316133061289327418861479409448871989720634;
    uint256 constant IC14y = 8784602901587726229121476871149323504863432964179754658337377615770444834209;
    
    uint256 constant IC15x = 3853155624544166247008982559736920182699330205183340794146640866685208821112;
    uint256 constant IC15y = 12700505587834560275316888830193535317200536471435717436389674998260798263915;
    
    uint256 constant IC16x = 4225137359576551513389965049324238691413021444193899991843813505156402933113;
    uint256 constant IC16y = 7764464430332464967095344251277606164491787013067740859066024928064971542353;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[16] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                
                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))
                
                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))
                
                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))
                
                g1_mulAccC(_pVk, IC15x, IC15y, calldataload(add(pubSignals, 448)))
                
                g1_mulAccC(_pVk, IC16x, IC16y, calldataload(add(pubSignals, 480)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            
            checkField(calldataload(add(_pubSignals, 352)))
            
            checkField(calldataload(add(_pubSignals, 384)))
            
            checkField(calldataload(add(_pubSignals, 416)))
            
            checkField(calldataload(add(_pubSignals, 448)))
            
            checkField(calldataload(add(_pubSignals, 480)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
